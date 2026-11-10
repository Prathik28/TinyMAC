/*
 * TinyMAC compute core: skewed feeders, 2x2 PE array and controller.
 *
 * Timing (t = step counter in RUN, starting at 0 on the START edge):
 *   feeder row i registers A[i][t-i]; feeder column j registers B[t-j][j]
 *   (zero outside 0..3). PE(i,j) sees operand pair k in cycle k+i+j+1 and
 *   accumulates it at the following edge, so the last pair (k=3, i=j=1)
 *   lands at the edge that ends t = 6. RUN therefore lasts 7 cycles.
 *
 * Feeders and PE pipelines carry zeros whenever not RUN, so stale data
 * can never leak into a new run.
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tinymac_core (
    input  wire         clk,
    input  wire         rst_n,
    input  wire [127:0] ab_flat,    // bytes 0..7 A[i][k] (4i+k), 8..15 B[k][j] (8+2k+j)
    input  wire         start,      // run request (caller guarantees !busy_top for user starts)
    input  wire         clear_acc,  // clear C at the start of this run
    input  wire         quiet,      // BIST-internal run: do not touch the user DONE flag
    input  wire         clr_flags,  // CTRL.CLR_FLAGS pulse
    input  wire         clr_done,   // BIST starting: drop DONE so BUSY and DONE are never both high
    output wire [79:0]  c_flat,     // 4 x 20-bit, index 2i+j
    output wire         busy,       // RUN in progress
    output wire         run_done,   // high for the one cycle after a run completes (C final)
    output reg          done,
    output reg          ovf,
    output reg  [1:0]   state,
    output reg  [2:0]   t
);

  localparam [1:0] S_IDLE = 2'd0, S_RUN = 2'd1, S_DONE = 2'd2;
  localparam [2:0] T_LAST = 3'd6;

  assign busy     = (state == S_RUN);
  assign run_done = (state == S_DONE);

  wire run = (state == S_RUN);
  wire go  = start && !busy;
  reg  quiet_run;

  // ---------------- controller ----------------
  always @(posedge clk) begin
    if (!rst_n) begin
      state     <= S_IDLE;
      t         <= 3'd0;
      done      <= 1'b0;
      quiet_run <= 1'b0;
    end else begin
      if (clr_flags || clr_done) done <= 1'b0;
      case (state)
        S_RUN: begin
          t <= t + 3'd1;
          if (t == T_LAST) begin
            state <= S_DONE;
            t     <= 3'd0;
            if (!quiet_run) done <= 1'b1;
          end
        end
        default: begin  // S_IDLE, S_DONE (one cycle), unused code
          state <= S_IDLE;
          if (go) begin
            state     <= S_RUN;
            t         <= 3'd0;
            quiet_run <= quiet;
            if (!quiet) done <= 1'b0;
          end
        end
      endcase
    end
  end

  // ---------------- feeders ----------------
  function [7:0] a_byte(input [127:0] ab, input integer i, input [2:0] tt);
    reg [2:0] k;
    begin
      k = tt - i[2:0];
      a_byte = (tt >= i[2:0] && k < 3'd4) ? ab[8*(4*i + {29'd0, k}) +: 8] : 8'h00;
    end
  endfunction

  function [7:0] b_byte(input [127:0] ab, input integer j, input [2:0] tt);
    reg [2:0] k;
    begin
      k = tt - j[2:0];
      b_byte = (tt >= j[2:0] && k < 3'd4) ? ab[8*(8 + 2*{29'd0, k} + j) +: 8] : 8'h00;
    end
  endfunction

  reg [7:0] a_feed0, a_feed1, b_feed0, b_feed1;
  always @(posedge clk) begin
    if (!rst_n) begin
      a_feed0 <= 8'h00; a_feed1 <= 8'h00;
      b_feed0 <= 8'h00; b_feed1 <= 8'h00;
    end else begin
      a_feed0 <= run ? a_byte(ab_flat, 0, t) : 8'h00;
      a_feed1 <= run ? a_byte(ab_flat, 1, t) : 8'h00;
      b_feed0 <= run ? b_byte(ab_flat, 0, t) : 8'h00;
      b_feed1 <= run ? b_byte(ab_flat, 1, t) : 8'h00;
    end
  end

  // ---------------- 2x2 array ----------------
  wire        clear = go && clear_acc;
  wire [7:0]  a00, a01_unused, a10, a11_unused;   // a passed right
  wire [7:0]  b00, b01, b10_unused, b11_unused;   // b passed down
  wire [19:0] acc00, acc01, acc10, acc11;
  wire        o00, o01, o10, o11;

  tinymac_pe pe00 (.clk(clk), .rst_n(rst_n), .clear(clear), .en(run),
                   .a_in(a_feed0), .b_in(b_feed0), .a_out(a00), .b_out(b00), .acc(acc00), .ovf(o00));
  tinymac_pe pe01 (.clk(clk), .rst_n(rst_n), .clear(clear), .en(run),
                   .a_in(a00), .b_in(b_feed1), .a_out(a01_unused), .b_out(b01), .acc(acc01), .ovf(o01));
  tinymac_pe pe10 (.clk(clk), .rst_n(rst_n), .clear(clear), .en(run),
                   .a_in(a_feed1), .b_in(b00), .a_out(a10), .b_out(b10_unused), .acc(acc10), .ovf(o10));
  tinymac_pe pe11 (.clk(clk), .rst_n(rst_n), .clear(clear), .en(run),
                   .a_in(a10), .b_in(b01), .a_out(a11_unused), .b_out(b11_unused), .acc(acc11), .ovf(o11));

  assign c_flat = {acc11, acc10, acc01, acc00};

  // sticky overflow flag
  always @(posedge clk) begin
    if (!rst_n)                     ovf <= 1'b0;
    else if (o00 | o01 | o10 | o11) ovf <= 1'b1;
    else if (clr_flags)             ovf <= 1'b0;
  end

  wire _unused = &{a01_unused, a11_unused, b10_unused, b11_unused, 1'b0};

`ifdef FORMAL
  // ---------------- formal properties ----------------
  reg f_past_valid = 1'b0;
  always @(posedge clk) f_past_valid <= 1'b1;

  // cycles since an accepted user START, to prove a bounded response
  reg       f_wait = 1'b0;
  reg [3:0] f_cnt  = 4'd0;
  always @(posedge clk) begin
    if (!rst_n) begin
      f_wait <= 1'b0;
      f_cnt  <= 4'd0;
    end else if (go && !quiet) begin
      f_wait <= 1'b1;
      f_cnt  <= 4'd0;
    end else if (f_wait) begin
      f_cnt <= f_cnt + 4'd1;
      if (state == S_DONE) f_wait <= 1'b0;
    end
  end

  always @(*) begin
    if (f_past_valid && rst_n) begin
      assert (state != 2'd3);                    // only IDLE / RUN / DONE are reachable
      assert (t <= T_LAST);
      if (state != S_RUN) assert (t == 3'd0);
      // DONE follows an accepted START within 8 cycles (7 RUN cycles + 1)
      if (f_wait) begin
        assert (state != S_IDLE);
        assert (!quiet_run);
        assert (f_cnt <= 4'd7);
        if (state == S_RUN)  assert (f_cnt == {1'b0, t});
        if (state == S_DONE) assert (done && f_cnt == 4'd7);
      end
    end
  end

  always @(posedge clk) begin
    if (f_past_valid && rst_n) cover (state == S_DONE && !quiet_run);
  end
`endif

endmodule
