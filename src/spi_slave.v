/*
 * TinyMAC SPI slave (mode 0, MSB first), single clk domain.
 * Command byte {RW, ADDR[6:0]}, address auto-increments per byte.
 * Reads insert one dummy byte (MISO = 0x00) after the command byte.
 * SCK / CS_N / MOSI are 2-FF synchronised; edges are detected in clk.
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module spi_slave (
    input  wire       clk,
    input  wire       rst_n,
    // raw (asynchronous) SPI pins
    input  wire       sck_i,
    input  wire       cs_n_i,
    input  wire       mosi_i,
    output reg        miso_o,
    // register interface
    output wire [6:0] rd_addr,   // address of the byte that will be loaded next
    input  wire [7:0] rd_data,   // combinational read of the register file
    output reg        wr_en,     // one-clk write strobe
    output reg  [6:0] wr_addr,
    output reg  [7:0] wr_data,
    output reg  [7:0] last_rx    // last byte received (debug)
);

  localparam [1:0] PH_CMD = 2'd0, PH_WRITE = 2'd1, PH_DUMMY = 2'd2, PH_READ = 2'd3;

  // 2-FF synchronisers (+1 stage for edge detection)
  reg [2:0] sck_q;
  reg [1:0] cs_q, mosi_q;
  always @(posedge clk) begin
    if (!rst_n) begin
      sck_q  <= 3'b000;
      cs_q   <= 2'b11;
      mosi_q <= 2'b00;
    end else begin
      sck_q  <= {sck_q[1:0], sck_i};
      cs_q   <= {cs_q[0], cs_n_i};
      mosi_q <= {mosi_q[0], mosi_i};
    end
  end

  wire sck_rise = sck_q[1] & ~sck_q[2];
  wire sck_fall = ~sck_q[1] & sck_q[2];
  wire cs_idle  = cs_q[1];  // CS_N high = not selected

  reg [1:0] phase;
  reg [2:0] bitcnt;
  reg [6:0] rx_shift;
  reg [7:0] tx_shift;
  reg [6:0] addr;

  assign rd_addr = addr;

  wire [7:0] rx_full = {rx_shift[6:0], mosi_q[1]};

  always @(posedge clk) begin
    if (!rst_n) begin
      phase    <= PH_CMD;
      bitcnt   <= 3'd0;
      rx_shift <= 7'h00;
      tx_shift <= 8'h00;
      addr     <= 7'h00;
      miso_o   <= 1'b0;
      wr_en    <= 1'b0;
      wr_addr  <= 7'h00;
      wr_data  <= 8'h00;
      last_rx  <= 8'h00;
    end else begin
      wr_en <= 1'b0;

      if (cs_idle) begin
        // not selected (or aborted mid-byte): drop all partial state
        phase    <= PH_CMD;
        bitcnt   <= 3'd0;
        tx_shift <= 8'h00;
        miso_o   <= 1'b0;
      end else begin
        if (sck_rise) begin
          rx_shift <= rx_full[6:0];
          bitcnt   <= bitcnt + 3'd1;
          if (bitcnt == 3'd7) begin
            last_rx <= rx_full;
            case (phase)
              PH_CMD: begin
                addr     <= rx_full[6:0];
                phase    <= rx_full[7] ? PH_DUMMY : PH_WRITE;
                tx_shift <= 8'h00;
              end
              PH_WRITE: begin
                wr_en   <= 1'b1;
                wr_addr <= addr;
                wr_data <= rx_full;
                addr    <= addr + 7'd1;
              end
              PH_DUMMY: begin
                phase    <= PH_READ;
                tx_shift <= rd_data;
                addr     <= addr + 7'd1;
              end
              default: begin  // PH_READ
                tx_shift <= rd_data;
                addr     <= addr + 7'd1;
              end
            endcase
          end
        end
        if (sck_fall) begin
          miso_o   <= tx_shift[7];
          tx_shift <= {tx_shift[6:0], 1'b0};
        end
      end
    end
  end

endmodule
