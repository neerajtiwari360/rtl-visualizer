module tb_counter;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst = 1, enable = 0;
    wire [7:0] count;
    counter dut(.*);
    initial begin
        $dumpfile("trace.vcd");
        $dumpvars(0, tb_counter);
        repeat (2) @(negedge clk);
        rst = 0; enable = 1;
        repeat (10) @(negedge clk);
        assert (count == 8'd10) else $fatal(1, "Counter mismatch");
        enable = 0;
        repeat (3) @(negedge clk);
        $display("PASS: counter reached 10 and stopped");
        $finish;
    end
endmodule
