module conv2d (
    input wire clk, rst, start,
    input wire [127:0] pixels,
    input wire [71:0] weights,
    output reg busy, done, valid,
    output reg [1:0] out_index,
    output reg signed [31:0] result,
    output reg [3:0] tap,
    output reg signed [31:0] accumulator,
    output wire signed [7:0] pixel_value, weight_value,
    output wire signed [15:0] product
);
    wire [3:0] pixel_index = ({3'b0, out_index[1]} + tap / 4'd3) * 4'd4
                              + {3'b0, out_index[0]} + tap % 4'd3;
    assign pixel_value = pixels[pixel_index * 8 +: 8];
    assign weight_value = weights[tap * 8 +: 8];
    assign product = pixel_value * weight_value;
    wire signed [31:0] extended_product = {{16{product[15]}}, product};
    always @(posedge clk) begin
        if (rst) begin
            busy <= 0; done <= 0; valid <= 0;
            out_index <= 0; tap <= 0; accumulator <= 0; result <= 0;
        end else begin
            valid <= 0;
            if (start && !busy) begin
                busy <= 1; done <= 0; out_index <= 0; tap <= 0; accumulator <= 0;
            end else if (busy) begin
                if (tap == 8) begin
                    result <= accumulator + extended_product;
                    valid <= 1; accumulator <= 0; tap <= 0;
                    if (out_index == 3) begin busy <= 0; done <= 1; end
                    else out_index <= out_index + 1;
                end else begin
                    accumulator <= accumulator + extended_product;
                    tap <= tap + 1;
                end
            end
        end
    end
endmodule
