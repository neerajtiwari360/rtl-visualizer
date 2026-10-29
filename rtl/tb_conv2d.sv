module tb_conv2d;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst = 1, start = 0;
    reg [127:0] pixels;
    reg [71:0] weights;
    wire busy, done, valid;
    wire [1:0] out_index;
    wire [3:0] tap;
    wire signed [31:0] result, accumulator;
    wire signed [7:0] pixel_value, weight_value;
    wire signed [15:0] product;
    reg [7:0] pixel_mem [0:15];
    reg [7:0] weight_mem [0:8];
    integer i, cycle = 0, index_before;
    conv2d dut(.*);
    initial begin
        $readmemh("pixels.hex", pixel_mem);
        $readmemh("weights.hex", weight_mem);
        for (i=0; i<16; i=i+1) pixels[i*8 +: 8] = pixel_mem[i];
        for (i=0; i<9; i=i+1) weights[i*8 +: 8] = weight_mem[i];
        $dumpfile("trace.vcd"); $dumpvars(0, tb_conv2d);
        repeat (2) @(negedge clk);
        rst = 0; start = 1;
        @(negedge clk); start = 0;
        repeat (100) begin
            @(posedge clk);
            if (busy) begin
                index_before = {30'b0, out_index};
                $write("MAC %0d %0d %0d %0d %0d %0d %0d\n", cycle,
                    out_index, tap, pixel_value, weight_value, product, accumulator);
                #1;
                if (valid) $display("OUT %0d %0d", index_before, result);
            end
            cycle = cycle + 1;
            if (done) $finish;
        end
        $fatal(1, "Simulation timed out");
    end
endmodule
