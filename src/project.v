/*
 * TinyMAC top level: SPI slave, register file, 2x2 systolic compute core, BIST.
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
  wire       bist_go_edge = bist_go_q[1] & ~bist_go_d;  // BIST_GO button, rising edge

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

  wire [79:0] c_flat;
  wire        core_busy, run_done, done, ovf;
  wire [1:0]  core_state;
  wire [2:0]  t;
  wire        bist_active, bist_run_start, bist_we, bist_done, bist_pass;
  wire [2:0]  bist_pair;
  wire [15:0] bist_wdata, lfsr, bist_sig;

  wire busy = core_busy | bist_active;
  reg  [15:0] cycle_cnt;

  // CTRL pulses are already suppressed by the register file while busy
  wire user_go = ctrl_pulse[0] && !busy;
  wire bist_go = (ctrl_pulse[2] | bist_go_edge) && !busy && !ctrl_pulse[0];

  tinymac_regs u_regs (
      .clk(clk), .rst_n(rst_n), .busy(busy),
      .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data),
      .bist_we(bist_we), .bist_pair(bist_pair), .bist_wdata(bist_wdata),
      .rd_addr(rd_addr), .rd_data(rd_data),
      .status({bist_pass, bist_done, ovf, done, busy}), .c_flat(c_flat),
      .cycle_cnt(cycle_cnt), .bist_sig(bist_sig),
      .ab_flat(ab_flat), .ctrl_pulse(ctrl_pulse)
  );

  tinymac_core u_core (
      .clk(clk), .rst_n(rst_n), .ab_flat(ab_flat),
      .start(user_go | bist_run_start),
      .clear_acc(bist_run_start | ctrl_pulse[1]),
      .quiet(bist_run_start),
      .clr_flags(ctrl_pulse[3]), .clr_done(bist_go),
      .c_flat(c_flat), .busy(core_busy), .run_done(run_done), .done(done), .ovf(ovf),
      .state(core_state), .t(t)
  );

  tinymac_bist u_bist (
      .clk(clk), .rst_n(rst_n), .go(bist_go), .clr_flags(ctrl_pulse[3]),
      .run_done(run_done), .c_flat(c_flat),
      .active(bist_active), .run_start(bist_run_start),
      .ab_we(bist_we), .ab_pair(bist_pair), .ab_wdata(bist_wdata),
      .lfsr(lfsr), .sig(bist_sig), .bist_done(bist_done), .bist_pass(bist_pass)
  );

  // FSM state for debug: 0 IDLE, 1 RUN, 2 DONE, 3 BIST
  wire [1:0] state = bist_active ? 2'd3 : core_state;

  // cycle counter: clock cycles of the last run or BIST
  always @(posedge clk) begin
    if (!rst_n)                  cycle_cnt <= 16'd0;
    else if (user_go | bist_go)  cycle_cnt <= 16'd0;
    else if (busy)               cycle_cnt <= cycle_cnt + 16'd1;
  end

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
      2'b00:   dbg_byte = {state, t[1:0], busy, done, ovf, bist_pass};
      2'b01:   dbg_byte = c_flat[7:0];  // C[0][0][7:0]
      2'b10:   dbg_byte = lfsr[7:0];
      default: dbg_byte = last_rx;
    endcase
  end

  assign uo_out  = {1'b0, hb_cnt[21], bist_pass, bist_done, ovf, done, busy, miso};
  assign uio_out = dbg_en ? dbg_byte : 8'h00;
  assign uio_oe  = {8{dbg_en}};

  wire _unused = &{ena, uio_in, ui_in[7], t[2], lfsr[15:8], 1'b0};

`ifdef FORMAL
  // ---------------- formal properties (top level, on the real pins) ----------------
  reg f_past_valid = 1'b0;
  always @(posedge clk) f_past_valid <= 1'b1;
  always @(*) if (!f_past_valid) assume (!rst_n);

  always @(*) begin
    if (f_past_valid && rst_n) begin
      assert (!(uo_out[1] && uo_out[2]));        // BUSY and DONE never both high
      assert (uo_out[7] == 1'b0);                // reserved output driven low
      assert (uio_oe == 8'h00 || uio_oe == 8'hFF);
      if (uio_oe == 8'h00) assert (uio_out == 8'h00);
    end
  end

  // uio_oe is 0x00 whenever DBG_EN has been low (2-FF synchroniser latency = 2 cycles)
  reg f_past2 = 1'b0;
  always @(posedge clk) f_past2 <= f_past_valid;
  always @(posedge clk) begin
    if (f_past2 && !$past(ui_in[4], 2)) assert (uio_oe == 8'h00);
  end
`endif

endmodule
