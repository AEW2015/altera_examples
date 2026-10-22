# Explicit one-shot SVG FPGA capture. No programming or RF/serial access here.
# argv: comma-separated payload counts, seed, noise amplitude, arc mode,
#       timeout seconds, summary-only flag, cable regex, capture-all-vectors flag

proc svg_read {master address} {
    # The component map is expressed in 32-bit words; SystemConsole master
    # services address bytes and require an explicit word count.
    return [lindex [master_read_32 $master [expr {$address * 4}] 1] 0]
}

proc svg_write {master address value} {
    master_write_32 $master [expr {$address * 4}] $value
}

proc svg_capture_vectors {master payload_count symbol_count wave_count frame_index} {
    puts "VECTOR_BEGIN\t$frame_index"
    puts "SYMBOL_HEADER\tindex\ttx_word\trx_word\tsource_bit\tdecoded_bit\ttx_node\trx_node"
    for {set index 0} {$index < $symbol_count} {incr index} {
        svg_write $master 6 $index
        set tx_word [svg_read $master 7]
        set rx_word [svg_read $master 8]
        set source_bit "-"
        set decoded_bit "-"
        if {$index < $payload_count} {
            set source_bit [svg_read $master 9]
            set decoded_bit [svg_read $master 10]
        }
        set tx_node [svg_read $master 11]
        set rx_node [svg_read $master 12]
        puts "SYMBOL\t$index\t$tx_word\t$rx_word\t$source_bit\t$decoded_bit\t$tx_node\t$rx_node"
    }
    puts "WAVE_HEADER\tindex\ttx_word\trx_word"
    for {set index 0} {$index < $wave_count} {incr index} {
        svg_write $master 6 $index
        set tx_word [svg_read $master 13]
        set rx_word [svg_read $master 14]
        puts "WAVE\t$index\t$tx_word\t$rx_word"
    }
    puts "VECTOR_END\t$frame_index"
}

set claimed 0
set master ""
set failure [catch {
    if {$argc != 8} {
        error "expected 8 arguments, received $argc"
    }
    set payload_counts [split [lindex $argv 0] ,]
    set base_seed [expr {wide([lindex $argv 1]) & 0xffffffff}]
    set noise_amplitude [expr {wide([lindex $argv 2])}]
    set arc_mode [expr {wide([lindex $argv 3])}]
    set timeout_seconds [expr {wide([lindex $argv 4])}]
    set summary_only [expr {wide([lindex $argv 5])}]
    set cable_regex [lindex $argv 6]
    set capture_all_vectors [expr {wide([lindex $argv 7])}]

    if {$base_seed == 0 || $noise_amplitude < 0 || $noise_amplitude > 30000 ||
        ($arc_mode != 0 && $arc_mode != 1) || $timeout_seconds < 1} {
        error "invalid seed, noise amplitude, waveform mode, or timeout"
    }

    set matches {}
    # Discovery can complete after the script starts in a fresh SystemConsole.
    # Retry only discovery; never replay a frame-start or a write transaction.
    set discovery_deadline [expr {[clock milliseconds] + 15000}]
    while {[clock milliseconds] < $discovery_deadline} {
        set paths [get_service_paths master]
        set matches {}
        foreach path $paths {
            if {[regexp -nocase -- $cable_regex $path]} {
                lappend matches $path
            }
        }
        if {[llength $matches] > 0} { break }
        after 250
    }
    if {[llength $matches] != 1} {
        error "cable selector matched [llength $matches] master paths; exactly one Atum A3 Nano JTAG master must match; discovered: $paths"
    }
    set selected_path [lindex $matches 0]
    puts "CABLE\t$selected_path"
    set master [claim_service master $selected_path ""]
    set claimed 1

    set fpga_id [svg_read $master 0]
    if {$fpga_id != 0x53564701} {
        error [format "wrong FPGA image ID 0x%08x (expected 0x53564701)" $fpga_id]
    }
    if {[svg_read $master 22] != 320 || [svg_read $master 23] != 16} {
        error "FPGA graph modem capabilities do not match 320 states and 16 samples per edge"
    }
    puts "IDENTITY\t$fpga_id\t320\t16"
    puts "CAPTURE_BEGIN"

    set frame_index 0
    foreach payload_count $payload_counts {
        set payload_count [expr {wide($payload_count)}]
        if {$payload_count < 1 || $payload_count > 256} {
            error "frame payload count must be in 1..256"
        }
        set frame_seed [expr {($base_seed + $frame_index) & 0xffffffff}]
        if {$frame_seed == 0} { set frame_seed 1 }

        svg_write $master 2 $payload_count
        svg_write $master 3 $noise_amplitude
        svg_write $master 4 $frame_seed
        svg_write $master 5 $arc_mode
        set read_payload [svg_read $master 2]
        set read_noise [svg_read $master 3]
        set read_seed [svg_read $master 4]
        set read_mode [svg_read $master 5]
        if {$read_payload != $payload_count || $read_noise != $noise_amplitude ||
            $read_seed != $frame_seed || $read_mode != $arc_mode} {
            error "frame $frame_index configuration readback mismatch"
        }
        puts "CONFIG\t$frame_index\t$read_payload\t$read_noise\t$read_seed\t$read_mode"

        svg_write $master 1 1
        set deadline [expr {[clock milliseconds] + 1000 * $timeout_seconds}]
        set status 0
        while {[clock milliseconds] < $deadline} {
            set status [svg_read $master 1]
            if {$status & 4} {
                error "FPGA reported an error during frame $frame_index (status=$status)"
            }
            if {($status & 2) && !($status & 1)} { break }
            after 10
        }
        if {(($status & 2) == 0) || ($status & 1)} {
            error "timeout waiting for frame $frame_index (status=$status)"
        }

        set cycles [svg_read $master 17]
        set symbol_errors [svg_read $master 15]
        set payload_errors [svg_read $master 16]
        set symbol_count [svg_read $master 18]
        set wave_count [svg_read $master 19]
        set metric_low [svg_read $master 20]
        set metric_high [svg_read $master 21]
        if {$symbol_count != $payload_count + 6 || $wave_count != 16 * $symbol_count} {
            error "frame $frame_index returned unexpected vector lengths"
        }
        puts "FRAME\t$frame_index\t$payload_count\t$frame_seed\t$noise_amplitude\t$arc_mode\t$status\t$cycles\t$symbol_errors\t$payload_errors\t$symbol_count\t$wave_count\t$metric_high\t$metric_low"
        set is_final [expr {$frame_index == [llength $payload_counts] - 1}]
        if {$is_final || ($capture_all_vectors && !$summary_only)} {
            svg_capture_vectors $master $payload_count $symbol_count $wave_count $frame_index
        }
        incr frame_index
    }
    puts "CAPTURE_END"
} message options]

if {$claimed} {
    if {[catch {release_service master $master}]} {
        catch {close_service master $master}
    }
}
if {$failure} {
    puts stderr "SVG_ERROR\t$message"
    exit 1
}
exit 0
