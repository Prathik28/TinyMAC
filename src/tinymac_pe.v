/*
 * TinyMAC processing element (output stationary).
 * Passes a right and b down with one register each; accumulates
 * a*b (signed 8x8 -> 16, sign-extended) into a 20-bit accumulator.
 * Overflow of the signed 20-bit add raises ovf for one cycle.
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tinymac_pe (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              clear,  // acc <= 0 (takes priority over en)
    input  wire              en,     // accumulate this cycle
    input  wire        [7:0] a_in,
    input  wire        [7:0] b_in,
    output reg         [7:0] a_out,
    output reg         [7:0] b_out,
    output reg        [19:0] acc,
    output reg               ovf     // pulse: this cycle's add overflowed
);

  wire signed [15:0] prod = $signed(a_in) * $signed(b_in);
  wire        [19:0] prod_ext = {{4{prod[15]}}, prod};
  wire        [19:0] sum = acc + prod_ext;
  // signed overflow: operands share a sign and the result's sign differs
  wire add_ovf = (acc[19] == prod_ext[19]) && (sum[19] != acc[19]);

  always @(posedge clk) begin
    if (!rst_n) begin
      a_out <= 8'h00;
      b_out <= 8'h00;
      acc   <= 20'd0;
      ovf   <= 1'b0;
    end else begin
      a_out <= a_in;
      b_out <= b_in;
      ovf   <= 1'b0;
      if (clear) begin
        acc <= 20'd0;
      end else if (en) begin
        acc <= sum;
        ovf <= add_ovf;
      end
    end
  end

endmodule
