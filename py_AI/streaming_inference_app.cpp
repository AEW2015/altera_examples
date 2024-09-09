// Copyright 2023 Intel Corporation.
//
// This software and the related documents are Intel copyrighted materials,
// and your use of them is governed by the express license under which they
// were provided to you ("License"). Unless the License provides otherwise,
// you may not use, modify, copy, publish, distribute, disclose or transmit
// this software or the related documents without Intel's prior written
// permission.
//
// This software and the related documents are provided as is, with no express
// or implied warranties, other than those that are expressly stated in the
// License.

#include "streaming_inference_app.h"
#include <fcntl.h>
#include <signal.h>
#include <sys/utsname.h>
#include <unistd.h>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <thread>
#include "dla_plugin_config.hpp"
#include <sys/mman.h>

using namespace std::chrono_literals;

std::ofstream StreamingInferenceApp::_resultsStream("results.txt");
std::mutex StreamingInferenceApp::_signalMutex;
std::condition_variable StreamingInferenceApp::_signalConditionVariable;
std::chrono::time_point<std::chrono::system_clock> StreamingInferenceApp::_startTime;

int main(int numParams, char* paramValues[]) {
  StreamingInferenceApp app(numParams, paramValues);

  try {
    app.Run();
  } catch (const std::exception& ex) {
    std::cerr << ex.what() << '\n';
  }
  return 0;
}

StreamingInferenceApp::StreamingInferenceApp(int numParams, char* paramValues[])
    : _commandLine(numParams, paramValues) {
  OsStartup();
  LoadClassNames();
}

StreamingInferenceApp::~StreamingInferenceApp() {
  timespec waitTimeout = {};
  if (_pCancelSemaphore) {
    // Reset the cancel semaphore
    int r = 0;
    do {
      r = ::sem_timedwait(_pCancelSemaphore, &waitTimeout);
    } while (r == 0);
    ::sem_close(_pCancelSemaphore);
  }

  if (_pReadyForImageStreamSemaphore) {
    // Reset the ready semaphore
    int r = 0;
    do {
      r = ::sem_timedwait(_pReadyForImageStreamSemaphore, &waitTimeout);
    } while (r == 0);
    ::sem_close(_pReadyForImageStreamSemaphore);
  }
}

void StreamingInferenceApp::Run() {
  std::filesystem::path pluginsFilename = "plugins.xml";

  std::string deviceName;
  std::string arch;
  std::string model;

  if (not _commandLine.GetOption("model", model) or not _commandLine.GetOption("arch", arch) or
      not _commandLine.GetOption("device", deviceName)) {
    return Usage();
  }

  std::filesystem::path architectureFilename = arch;
  std::filesystem::path compiledModelFilename = model;

  if (not CheckFileExists(architectureFilename, "architecture") or not CheckFileExists(pluginsFilename, "plugins") or
      not CheckFileExists(compiledModelFilename, "compiled model")) {
    return;
  }

  InferenceEngine::Core inferenceEngine(pluginsFilename);

  // Setup CoreDLA private configuration parameters
  const std::map<std::string, std::string> configParameters;
  inferenceEngine.SetConfig({{DLIAPlugin::properties::arch_path.name(), architectureFilename}}, "FPGA");

  // If dropSourceBuffers is 0, no input buffers are dropped
  // If dropSourceBuffers is 1, then 1 buffer is processed, 1 gets dropped
  // If dropSourceBuffers is 2, then 1 buffer is processed, 2 get dropped, etc.
  uint32_t dropSourceBuffers = 0;

  inferenceEngine.SetConfig({{DLIAPlugin::properties::streaming_drop_source_buffers.name(), std::to_string(dropSourceBuffers)},
                             {DLIAPlugin::properties::external_streaming.name(), CONFIG_VALUE(YES)}},
                            "FPGA");

  std::ifstream inputFile(compiledModelFilename, std::fstream::binary);
  if (not inputFile) {
    std::cout << "Failed to load compiled model file.\n";
    return;
  }

  // Load the model to the device
  InferenceEngine::ExecutableNetwork importedNetwork = inferenceEngine.ImportNetwork(inputFile, deviceName, {});

  // The plugin defines the number of inferences requests required for streaming
  uint32_t numStreamingInferenceRequests = importedNetwork.GetMetric(DLIAPlugin::properties::num_streaming_inference_requests.name()).as<uint32_t>();
  const std::string cancelSemaphoreName = importedNetwork.GetMetric(DLIAPlugin::properties::cancel_semaphore_name.name()).as<std::string>();
  _cancelSemaphoreName = cancelSemaphoreName;

  for (uint32_t i = 0; i < numStreamingInferenceRequests; i++) {
    auto spInferenceData = std::make_shared<SingleInferenceData>(this, importedNetwork, i);
    _inferences.push_back(spInferenceData);
  }

  // Start the inference requests. Streaming inferences will reschedule
  // themselves when complete
  for (auto& inference : _inferences) {
    inference->StartAsync();
  }

  std::cout << "Ready to start image input stream.\n";

  // Signal the image streaming app that we are ready, so it can
  // begin transferring files
  SetReadyForImageStreamSemaphore();

  // Wait until Ctrl+C
  bool done = false;
  while (not done) {
    std::unique_lock<std::mutex> lock(_signalMutex);
    done = (_signalConditionVariable.wait_for(lock, 1000ms) != std::cv_status::timeout);
  }

  SetShutdownSemaphore();

  for (auto& inference : _inferences) {
    inference->Cancel();
  }

  _inferences.clear();
}

void StreamingInferenceApp::SetShutdownSemaphore() {
  _pCancelSemaphore = ::sem_open(_cancelSemaphoreName.c_str(), O_CREAT, 0644, 0);
  if (_pCancelSemaphore) {
    ::sem_post(_pCancelSemaphore);
  }
}

void StreamingInferenceApp::SetReadyForImageStreamSemaphore() {
  _pReadyForImageStreamSemaphore = ::sem_open("/CoreDLA_ready_for_streaming", O_CREAT, 0644, 0);
  if (_pReadyForImageStreamSemaphore) {
    ::sem_post(_pReadyForImageStreamSemaphore);
  }
}

void StreamingInferenceApp::Usage() {
  std::cout << "Usage:\n";
  std::cout << "\tstreaming_inference_app -model=<model> -arch=<arch> -device=<device>\n\n";
  std::cout << "Where:\n";
  std::cout << "\t<model>    is the compiled model binary file, eg /home/root/resnet-50-tf/RN50_Performance_no_folding.bin\n";
  std::cout << "\t<arch>     is the architecture file, eg /home/root/resnet-50-tf/A10_Performance.arch\n";
  std::cout << "\t<device>   is the OpenVINO device ID, eg HETERO:FPGA or HETERO:FPGA,CPU\n";
}

bool StreamingInferenceApp::CheckFileExists(const std::filesystem::path& filename, const std::string& message) {
  if (not std::filesystem::exists(filename)) {
    std::cout << "Can't find " << message << ", '" << filename.c_str() << "'\n";
    return false;
  }

  return true;
}

////////////

std::atomic<uint32_t> SingleInferenceData::_atomic{0};
uint32_t SingleInferenceData::_numResults = 0;

SingleInferenceData::SingleInferenceData(StreamingInferenceApp* pApp,
                                         InferenceEngine::ExecutableNetwork& importedNetwork,
                                         uint32_t index)
    : _pApp(pApp), _importedNetwork(importedNetwork), _index(index), _inferenceCount(0) {
  // Set up output blob
  InferenceEngine::ConstOutputsDataMap outputsInfo = importedNetwork.GetOutputsInfo();
  std::shared_ptr<const InferenceEngine::Data> spOutputInfo = outputsInfo.begin()->second;
  std::string outputName = outputsInfo.begin()->first;

  _spOutputBlob = CreateOutputBlob(spOutputInfo);

  // Create an inference request and set its completion callback
  _inferenceRequest = importedNetwork.CreateInferRequest();
  auto inferenceRequestCompleteCB = [=]() { ProcessResult(); };
  _inferenceRequest.SetCompletionCallback(inferenceRequestCompleteCB);

  // Assign the output blob to the inference request
  _inferenceRequest.SetBlob(outputName, _spOutputBlob);
}

std::shared_ptr<InferenceEngine::Blob> SingleInferenceData::CreateOutputBlob(
    std::shared_ptr<const InferenceEngine::Data> spOutputInfo) {
  const InferenceEngine::TensorDesc& outputTensorDesc = spOutputInfo->getTensorDesc();
  std::shared_ptr<InferenceEngine::Blob> pOutputBob = InferenceEngine::make_shared_blob<float>(outputTensorDesc);
  pOutputBob->allocate();

  InferenceEngine::MemoryBlob::Ptr pMemoryBlob = InferenceEngine::as<InferenceEngine::MemoryBlob>(pOutputBob);
  if (pMemoryBlob) {
    auto lockedMemory = pMemoryBlob->wmap();
    float* pOutputBlobData = lockedMemory.as<float*>();
    if (pOutputBlobData) {
      size_t outputSize = pOutputBob->size();
      for (size_t i = 0; i < outputSize; i++) {
        pOutputBlobData[i] = 0.0f;
      }
    }
  }

  return pOutputBob;
}

void SingleInferenceData::StartAsync() {
  _inferenceCount = _atomic++;
  _inferenceRequest.StartAsync();
}

void SingleInferenceData::Wait() { _inferenceRequest.Wait(); }

void SingleInferenceData::Cancel() { _inferenceRequest.Cancel(); }

class ResultItem {
 public:
  uint32_t _index;
  float _score;
  bool operator<(const ResultItem& other) { return (_score > other._score); }
};

// Called when inference request has completed
void SingleInferenceData::ProcessResult() {
  if (_pApp and _pApp->IsCancelling()) {
    return;
  }
  _numResults++;
  if (_numResults == 1) {
    StreamingInferenceApp::_startTime = std::chrono::system_clock::now();
  } else if (_numResults == 101) {
    // The inference rate is calculated afer 100 results have been received
    auto endTime = std::chrono::system_clock::now();
    auto duration = endTime - StreamingInferenceApp::_startTime;
    double durationMS = (double)std::chrono::duration_cast<std::chrono::milliseconds>(duration).count();
    double durationSecondsOne = durationMS / 100000.0;
    double rate = 1.0 / durationSecondsOne;
    std::cout << "Inference rate = " << rate << '\n';
  }

  size_t outputSize = _spOutputBlob->size();
  float* pOutputData = _spOutputBlob->buffer().as<float*>();
  if (!pOutputData) {
    return;
  }
  std::vector<ResultItem> results;
  for (size_t i = 0; i < outputSize; i++) {
    results.push_back({(uint32_t)i, pOutputData[i]});
  }

  std::sort(results.begin(), results.end());
  std::stringstream fileString;
  std::stringstream outString;
  bool flushFile = false;

  int fd = -1;
  if ((fd = open("shared.mem", O_RDWR, 0)) == -1)
      {
      printf("unable to open shared.mem\n");
      return;
      }
  // open the file in shared memory
  uint32_t* shared = (uint32_t*) mmap(NULL, 64, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);

  

  if (_numResults <= 1000) {
    fileString << "Result: image[" << _numResults << "]\n";
    fileString << std::fixed << std::setprecision(1);
    for (size_t i = 0; i < 5; i++) {
      std::string className = _pApp->_imageNetClasses[results[i]._index];
      float score = results[i]._score * 100.0f;
      if (i == 0) {
        outString << _numResults << " - " << className << ", score = " << score << '\n';
      }
      fileString << (i + 1) << ". " << className << ", score = " << score << '\n';
      shared[i*2 + 0] = results[i]._index;
      shared[i*2 + 1] = (uint32_t)score;
    }

    // End and flush
    fileString << '\n';
  } else {
    outString << std::fixed << std::setprecision(1);
    std::string className = _pApp->_imageNetClasses[results[0]._index];
    float score = results[0]._score * 100.0f;
    outString << _numResults << " - " << className << ", score = " << score << '\n';
  }

  if (_numResults == 1001) {
    fileString << "End of results capture\n";
    flushFile = true;
  }

  // Output strings
  std::string writeFileString = fileString.str();
  if (not writeFileString.empty()) {
    StreamingInferenceApp::_resultsStream << writeFileString;
    if (flushFile) {
      StreamingInferenceApp::_resultsStream << std::endl;
    }
  }


  std::cout << outString.str();

  // Start again
  StartAsync();
}

void StreamingInferenceApp::LoadClassNames() {
  _imageNetClasses.resize(1001);

  bool validClassFile = false;
  std::filesystem::path classNameFilePath = "categories.txt";
  if (std::filesystem::exists(classNameFilePath)) {
    size_t classIndex = 0;
    std::ifstream classNameStream(classNameFilePath);
    if (classNameStream) {
      std::string className;
      while (std::getline(classNameStream, className)) {
        if (classIndex < 1001) _imageNetClasses[classIndex] = className;

        classIndex++;
      }

      validClassFile = (classIndex == 1001);
      if (not validClassFile) {
        std::cout << "Ignoring the categories.txt file. The file is expected to be a text file "
                     "with 1000 lines.\n";
      }
    }
  } else {
    std::cout << "No categories.txt file found. This file should contain 1000\n"
                 "lines, with the name of each category on each line.\n";
  }

  if (not validClassFile) {
    _imageNetClasses[0] = "NONE";
    for (size_t i = 1; i <= 1000; i++) {
      _imageNetClasses[i] = "Image class #" + std::to_string(i);
    }
  }
}

static void SigIntHandler(int) {
  std::cout << "\nCtrl+C detected. Shutting down application\n";
  std::lock_guard<std::mutex> lock(StreamingInferenceApp::_signalMutex);
  StreamingInferenceApp::_signalConditionVariable.notify_one();
}

void StreamingInferenceApp::OsStartup() {
  // Ctrl+C will exit the application
  signal(SIGINT, SigIntHandler);
}
