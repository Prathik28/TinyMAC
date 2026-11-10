/*
 * TinyMAC register file / address decode.
 * 0x00 CTRL (W, self-clearing)  0x01 STATUS (R)  0x02 ID (R)  0x03 SCRATCH (R/W)
 * 0x10-0x17 A  0x18-0x1F B  0x20-0x2B C (R)  0x30-0x31 CYCLE_CNT  0x32-0x33 BIST_SIG
 * Writes to A, B and CTRL are ignored while busy.
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tinymac_regs (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         busy,
    // write port (from SPI)
    input  wire         wr_en,
    input  wire [6:0]   wr_addr,
    input  wire [7:0]   wr_data,
    // read port (combinational)
    input  wire [6:0]   rd_addr,
    output reg  [7:0]   rd_data,
    // status / result inputs
    input  wire [4:0]   status,       // {BIST_PASS, BIST_DONE, OVF, DONE, BUSY}
    input  wire [79:0]  c_flat,       // 4 x 20-bit, index 2*i+j
    input  wire [15:0]  cycle_cnt,
    input  wire [15:0]  bist_sig,
    // outputs
    output wire [127:0] ab_flat,      // bytes 0..7 = A[i][k] (4i+k), 8..15 = B[k][j] (2k+j)
    output reg  [3:0]   ctrl_pulse    // {CLR_FLAGS, BIST_START, CLEAR_ACC, START}
);

  localparam [7:0] ID_VALUE = 8'hA5;

  reg [127:0] ab;
  reg [7:0]   scratch;
  assign ab_flat = ab;

  wire wr_ctrl = wr_en && (wr_addr == 7'h00) && !busy;
  wire wr_ab   = wr_en && (wr_addr[6:4] == 3'b001) && !busy;  // 0x10-0x1F
  wire [3:0] ab_idx = wr_addr[3:0];  // 0x10..0x1F -> 0..15

  always @(posedge clk) begin
    if (!rst_n) begin
      ab         <= 128'd0;
      scratch    <= 8'h00;
      ctrl_pulse <= 4'd0;
    end else begin
      ctrl_pulse <= wr_ctrl ? wr_data[3:0] : 4'd0;
      if (wr_en && wr_addr == 7'h03) scratch <= wr_data;
      if (wr_ab) ab[{ab_idx, 3'b000} +: 8] <= wr_data;
    end
  end

  // sign-extend each 20-bit accumulator to 24 bits
  wire [23:0] c0 = {{4{c_flat[19]}}, c_flat[19:0]};
  wire [23:0] c1 = {{4{c_flat[39]}}, c_flat[39:20]};
  wire [23:0] c2 = {{4{c_flat[59]}}, c_flat[59:40]};
  wire [23:0] c3 = {{4{c_flat[79]}}, c_flat[79:60]};

  always @(*) begin
    rd_data = 8'h00;
    case (rd_addr)
      7'h01: rd_data = {3'b000, status};
      7'h02: rd_data = ID_VALUE;
      7'h03: rd_data = scratch;
      7'h20: rd_data = c0[7:0];
      7'h21: rd_data = c0[15:8];
      7'h22: rd_data = c0[23:16];
      7'h23: rd_data = c1[7:0];
      7'h24: rd_data = c1[15:8];
      7'h25: rd_data = c1[23:16];
      7'h26: rd_data = c2[7:0];
      7'h27: rd_data = c2[15:8];
      7'h28: rd_data = c2[23:16];
      7'h29: rd_data = c3[7:0];
      7'h2A: rd_data = c3[15:8];
      7'h2B: rd_data = c3[23:16];
      7'h30: rd_data = cycle_cnt[7:0];
      7'h31: rd_data = cycle_cnt[15:8];
      7'h32: rd_data = bist_sig[7:0];
      7'h33: rd_data = bist_sig[15:8];
      default: begin
        if (rd_addr[6:4] == 3'b001) rd_data = ab[{rd_addr[3:0], 3'b000} +: 8];  // 0x10-0x1F
      end
    endcase
  end

endmodule
