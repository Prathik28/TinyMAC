/*
 * TinyMAC top level (phase 1: SPI slave + register file; compute core to follow).
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_prathik28_tinymac (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  // ---- input synchronisers (SPI pins are synchronised inside spi_slave) ----
  reg [1:0] bist_go_q, dbg_en_q;
  reg [3:0] dbg_sel_q;  // 2 bits x 2 stages
  reg       bist_go_d;
  always @(posedge clk) begin
    if (!rst_n) begin
      bist_go_q <= 2'b00;
      bist_go_d <= 1'b0;
      dbg_en_q  <= 2'b00;
      dbg_sel_q <= 4'b0000;
    end else begin
      bist_go_q <= {bist_go_q[0], ui_in[3]};
      bist_go_d <= bist_go_q[1];
      dbg_en_q  <= {dbg_en_q[0], ui_in[4]};
      dbg_sel_q <= {dbg_sel_q[1:0], ui_in[6:5]};
    end
  end
  wire       dbg_en  = dbg_en_q[1];
  wire [1:0] dbg_sel = dbg_sel_q[3:2];
  wire       bist_go_edge = bist_go_q[1] & ~bist_go_d;  // used once BIST is added

  // ---- SPI + registers ----
  wire        miso;
  wire [6:0]  rd_addr, wr_addr;
  wire [7:0]  rd_data, wr_data, last_rx;
  wire        wr_en;
  wire [127:0] ab_flat;
  wire [3:0]  ctrl_pulse;

  spi_slave u_spi (
      .clk(clk), .rst_n(rst_n),
      .sck_i(ui_in[0]), .cs_n_i(ui_in[1]), .mosi_i(ui_in[2]), .miso_o(miso),
      .rd_addr(rd_addr), .rd_data(rd_data),
      .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data),
      .last_rx(last_rx)
  );

  tinymac_regs u_regs (
      .clk(clk), .rst_n(rst_n), .busy(1'b0),
      .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data),
      .rd_addr(rd_addr), .rd_data(rd_data),
      .status(5'd0), .c_flat(80'd0), .cycle_cnt(16'd0), .bist_sig(16'd0),
      .ab_flat(ab_flat), .ctrl_pulse(ctrl_pulse)
  );

  // ---- heartbeat: clk / 2^22 blink ----
  reg [21:0] hb_cnt;
  always @(posedge clk) begin
    if (!rst_n) hb_cnt <= 22'd0;
    else        hb_cnt <= hb_cnt + 22'd1;
  end

  // ---- debug bus ----
  reg [7:0] dbg_byte;
  always @(*) begin
    case (dbg_sel)
      2'b00:   dbg_byte = 8'h00;       // {state, k, BUSY, DONE, OVF, BIST_PASS} - compute core pending
      2'b01:   dbg_byte = 8'h00;       // C[0][0][7:0] - compute core pending
      2'b10:   dbg_byte = 8'h00;       // LFSR[7:0] - BIST pending
      default: dbg_byte = last_rx;
    endcase
  end

  assign uo_out  = {1'b0, hb_cnt[21], 1'b0, 1'b0, 1'b0, 1'b0, 1'b0, miso};
  assign uio_out = dbg_en ? dbg_byte : 8'h00;
  assign uio_oe  = {8{dbg_en}};

  wire _unused = &{ena, uio_in, ui_in[7], ab_flat, ctrl_pulse, bist_go_edge, 1'b0};

endmodule
