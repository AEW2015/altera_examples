
variable socket_instance
variable connection
variable bus

proc start_server {{port 8953}} {
    variable socket_instance

    set socket_instance [socket -server ConnAccept $port]
    
    puts "Started Socket Server on port - $port"
}

proc ConnAccept {sock addr port} {           # Make a proc to accept connections
    variable connection   
    
    puts "Accept $sock from $addr port $port"
    set connection(addr,$sock) [list $addr $port]    

    fconfigure $sock -buffering line
    fileevent $sock readable [list IncomingCommand $sock]
}

proc IncomingCommand {sock} {
    variable connection

    if {[eof $sock] || [catch {gets $sock command}]} {
        close $sock
        puts "Close $connection(addr,$sock)"		
        unset connection(addr,$sock)
    } else {
        catch { linsert [eval $command] end EOF} result
        puts $sock $result
    }
}

proc stop_server {} {
    variable socket_instance
    
    close $socket_instance
}


proc open_bus {bus_id} {

    variable bus
    get_service_paths master
    set bus [ lindex [get_service_paths master] $bus_id]
    
    open_service master $bus
    
    jtag_debug_reset_system $bus
    
    return $bus
}

proc read_32 {addr length} {
    variable bus
    master_read_32 $bus $addr $length
}

proc write_32 {addr data} {
    variable bus
    master_write_32 $bus $addr $data
}

proc jtag_rst { } {
    variable bus
     jtag_debug_reset_system $bus
}

start_server