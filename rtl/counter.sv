module counter(input wire clk, rst, enable, output reg [7:0] count);
    always @(posedge clk) begin
        if (rst) count <= 8'd0;
        else if (enable) count <= count + 8'd1;
    end
endmodule
