![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/formal/badge.svg)

# TinyMAC: 2x2 INT8 systolic accelerator

A small matrix-multiply accelerator for Tiny Tapeout (GF180MCU, 2x2 tiles, 20 MHz): multiplies a 2x4 INT8 matrix by a 4x2 INT8 matrix over an SPI register interface, with overflow detection, a built-in self-test and a debug bus.

- [Read the documentation for project](docs/info.md): how it works, register map, how to test, bring-up checklist
- `src/`: Verilog (SPI slave, register file, compute core, PEs, BIST, top level)
- `test/`: cocotb testbench and NumPy model (`make`), coverage script (`./coverage.sh`)
- `formal/`: SymbiYosys proofs (`sby -f tinymac.sby`)

## What is Tiny Tapeout? 

Tiny Tapeout is an educational project that aims to make it easier and cheaper than ever to get your digital and analog designs manufactured on a real chip.

To learn more and get started, visit https://tinytapeout.com.

## Enable GitHub actions to build the results page

- [Enabling GitHub Pages](https://tinytapeout.com/faq/#my-github-action-is-failing-on-the-pages-part)

## Resources

- [FAQ](https://tinytapeout.com/faq/)
- [Digital design lessons](https://tinytapeout.com/digital_design/)
- [Learn how semiconductors work](https://tinytapeout.com/siliwiz/)
- [Join the community](https://tinytapeout.com/discord)
- [Build your design locally](https://www.tinytapeout.com/guides/local-hardening/)

## What next?

- [Submit your design to the next shuttle](https://app.tinytapeout.com/).
- Edit [this README](README.md) and explain your design, how it works, and how to test it.
- Share your project on your social network of choice:
  - LinkedIn [#tinytapeout](https://www.linkedin.com/search/results/content/?keywords=%23tinytapeout) [@TinyTapeout](https://www.linkedin.com/company/100708654/)
  - Mastodon [#tinytapeout](https://chaos.social/tags/tinytapeout) [@matthewvenn](https://chaos.social/@matthewvenn)
  - X (formerly Twitter) [#tinytapeout](https://twitter.com/hashtag/tinytapeout) [@tinytapeout](https://twitter.com/tinytapeout)
  - Bluesky [@tinytapeout.com](https://bsky.app/profile/tinytapeout.com)
