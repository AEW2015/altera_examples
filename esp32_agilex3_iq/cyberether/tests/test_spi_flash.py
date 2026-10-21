"""SPI builds cannot accidentally be flashed to an installed TX/RFS2 profile."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from flash_esp32 import images
class SPIFlash(unittest.TestCase):
 def test_spi_profiles_are_b_only_and_keep_rom_console(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'config').mkdir()
   for project in ('esp32_spi_probe','atum_rf_suite'):
    (root/'project_description.json').write_text(json.dumps(dict(target='esp32',project_name=project)))
    (root/'CMakeCache.txt').write_text('IQ_SPI_RX_PROFILE:BOOL=ON\n' if project=='atum_rf_suite' else '')
    cfg=dict(ESP_CONSOLE_UART_TX_GPIO=1,ESP_CONSOLE_UART_RX_GPIO=3,ESP_SDR_UART_TX_PIN=1,ESP_SDR_UART_RX_PIN=3)
    (root/'config/sdkconfig.json').write_text(json.dumps(cfg))
    files={'0x1000':'boot.bin','0x8000':'partition.bin','0x10000':'app.bin'}
    for name in files.values():(root/name).write_bytes(b'fixture')
    (root/'flasher_args.json').write_text(json.dumps(dict(flash_files=files)))
    images(root,'pmod-b')
    for module in ('pmod-a','pmod','rfs2'):
     with self.assertRaisesRegex(ValueError,'pmod-b only'):images(root,module)
    cfg['ESP_CONSOLE_UART_DEFAULT']=True
    cfg.pop('ESP_CONSOLE_UART_TX_GPIO');cfg.pop('ESP_CONSOLE_UART_RX_GPIO')
    (root/'config/sdkconfig.json').write_text(json.dumps(cfg));images(root,'pmod-b')
    cfg['ESP_CONSOLE_UART_DEFAULT']=False
    cfg['ESP_CONSOLE_UART_TX_GPIO']=17
    (root/'config/sdkconfig.json').write_text(json.dumps(cfg))
    with self.assertRaises(ValueError):images(root,'pmod-b')
if __name__=='__main__':unittest.main()
