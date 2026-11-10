/*
 * TinyMAC built-in self-test.
 *
 * Per iteration (x64):
 *   FILL  8 cycles: write LFSR state to A/B bytes {2n+1, 2n} = {lfsr[15:8], lfsr[7:0]},
 *                   step the LFSR once per cycle (it is never reseeded between iterations)
 *   START 1 cycle : request a quiet compute run with CLEAR_ACC
 *   WAIT          : until the core reports run_done (C final)
 *   FOLD  4 cycles: misr <= step(misr) ^ (acc[15:0] ^ acc[19:16]) for C00, C01, C10, C11
 * Then latch the signature, compare with GOLDEN_SIG, set BIST_DONE / BIST_PASS.
 *
 * LFSR / MISR polynomial x^16 + x^14 + x^13 + x^11 + 1 (Fibonacci, shift right),
 * seed 0xACE1, MISR starts at 0. GOLDEN_SIG comes from test/model.py (python model.py).
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tinymac_bist (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        go,          // start request (caller guarantees not busy)
    input  wire        clr_flags,   // CTRL.CLR_FLAGS pulse
    input  wire        run_done,    // from core
    input  wire [79:0] c_flat,      // from core
    output reg         active,      // BIST in progress (counts as BUSY)
    output reg         run_start,   // pulse: start a quiet, clearing compute run
    output reg         ab_we,       // write 2 bytes of A/B this cycle
    output reg  [2:0]  ab_pair,     // byte pair index (bytes 2*pair, 2*pair+1)
    output wire [15:0] ab_wdata,    // {byte 2*pair+1, byte 2*pair}
    output reg  [15:0] lfsr,
    output reg  [15:0] sig,         // BIST_SIG register
    output reg         bist_done,
    output reg         bist_pass
);

  localparam [15:0] SEED       = 16'hACE1;
  localparam [15:0] GOLDEN_SIG = 16'hB003;

  localparam [2:0] B_IDLE = 3'd0, B_FILL = 3'd1, B_START = 3'd2, B_WAIT = 3'd3,
                   B_FOLD = 3'd4, B_FINISH = 3'd5;

  function [15:0] step(input [15:0] x);
    step = {x[0] ^ x[2] ^ x[3] ^ x[5], x[15:1]};
  endfunction

  reg [2:0]  bstate;
  reg [2:0]  cnt;
  reg [5:0]  iter;
  reg [15:0] misr;

  assign ab_wdata = lfsr;

  // accumulator selected for folding: cnt 0..3 -> C00, C01, C10, C11
  wire [19:0] acc_sel = c_flat[20*cnt[1:0] +: 20];
  wire [15:0] fold    = acc_sel[15:0] ^ {12'd0, acc_sel[19:16]};

  always @(posedge clk) begin
    if (!rst_n) begin
      bstate    <= B_IDLE;
      cnt       <= 3'd0;
      iter      <= 6'd0;
      misr      <= 16'd0;
      lfsr      <= SEED;
      sig       <= 16'd0;
      active    <= 1'b0;
      run_start <= 1'b0;
      ab_we     <= 1'b0;
      ab_pair   <= 3'd0;
      bist_done <= 1'b0;
      bist_pass <= 1'b0;
    end else begin
      run_start <= 1'b0;
      ab_we     <= 1'b0;
      if (clr_flags) begin
        bist_done <= 1'b0;
        bist_pass <= 1'b0;
      end

      case (bstate)
        B_IDLE: begin
          if (go) begin
            bstate    <= B_FILL;
            active    <= 1'b1;
            lfsr      <= SEED;
            misr      <= 16'd0;
            iter      <= 6'd0;
            cnt       <= 3'd0;
            bist_done <= 1'b0;
            bist_pass <= 1'b0;
          end
        end
        B_FILL: begin
          // ab_we/ab_pair are registered, so the write happens next cycle using the
          // LFSR value of that cycle; the LFSR steps on the same edge (see below).
          ab_we   <= 1'b1;
          ab_pair <= cnt;
          if (cnt == 3'd7) begin
            bstate <= B_START;
            cnt    <= 3'd0;
          end else begin
            cnt <= cnt + 3'd1;
          end
        end
        B_START: begin
          run_start <= 1'b1;
          bstate    <= B_WAIT;
        end
        B_WAIT: begin
          if (run_done) bstate <= B_FOLD;
        end
        B_FOLD: begin
          misr <= step(misr) ^ fold;
          if (cnt == 3'd3) begin
            cnt  <= 3'd0;
            iter <= iter + 6'd1;
            bstate <= (iter == 6'd63) ? B_FINISH : B_FILL;
          end else begin
            cnt <= cnt + 3'd1;
          end
        end
        B_FINISH: begin
          sig       <= misr;
          bist_pass <= (misr == GOLDEN_SIG);
          bist_done <= 1'b1;
          active    <= 1'b0;
          bstate    <= B_IDLE;
        end
        default: bstate <= B_IDLE;
      endcase

      // step the LFSR in the cycle the registered write is performed
      if (ab_we) lfsr <= step(lfsr);
    end
  end

endmodule
