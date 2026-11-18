# World news in one image — Wednesday 18 November 2026

[![news-image-20261118](https://make.fun/badge/news-image-20261118.svg)](https://make.fun/c/news-image-20261118)
[![rank](https://make.fun/badge/news-image-20261118/godobox/news-image-20261118/rank.svg)](https://make.fun/c/news-image-20261118)
[![reward](https://make.fun/badge/news-image-20261118/godobox/news-image-20261118/reward.svg)](https://make.fun/c/news-image-20261118)

Entry for the [make.fun news-image contest for 18 November 2026](https://make.fun/c/news-image-20261118).

`main.py` draws one 1024×1024 news board summing up the world's news of
**Wednesday 18 November 2026** and writes it to `/output/entry.png`.

## Stories

1. **Diplomacy · China** — Trump, Xi and Putin gather for APEC in Shenzhen; first three-way talks set for Thursday.
2. **Conflict · Gulf** — Iran strikes at US bases in Kuwait and Bahrain after the US raid on Qeshm Island.
3. **War · Ukraine/Russia** — Kerch Bridge road span lies broken in the sea after Ukrainian strikes.
4. **Politics · US** — Democrat Mary Peltola wins Alaska's Senate seat; Democrats hold 56–44.
5. **Health · DR Congo** — Ebola outbreak passes 11,000 cases and 5,400 deaths (WHO).
6. **Science · Space** — Voyager 1 becomes the first human-made object one light-day from Earth.
7. **Disaster · South Pacific** — Category 5 Cyclone Xavier hits the northern Cook Islands.
8. **Middle East · Gaza** — Board of Peace report faults both Israel and Hamas.

## How it works

Python 3 standard library only — no packages, no network, no clock, no randomness:

- an anti-aliased **vector stroke font** (upper/lower case, digits, punctuation) defined as
  lines and arcs and rendered by distance-to-segment coverage;
- hand-drawn **icons** for every story (filled polygons with scanline anti-aliasing);
- a minimal **PNG encoder** (`zlib` + CRC-checked chunks).

Two runs produce byte-identical output.

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## License

MIT — see [LICENSE](LICENSE).
