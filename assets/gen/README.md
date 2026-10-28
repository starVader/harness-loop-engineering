# Diagram sources

`stage_flows.py` draws `assets/stageN_flow.svg` (stages 1-8) from `flowgen.py`'s
small node/edge layout. `final_architecture.svg` is hand-written SVG. Edit,
then regenerate the PNGs from the repo root:

```
cd assets/gen && python3 stage_flows.py .. && cd .. && for s in 1 2 3 4 5 6 7 8; do rsvg-convert -z 1.5 stage${s}_flow.svg -o stage${s}_flow.png; done && rsvg-convert -z 2 final_architecture.svg -o final_architecture.png
```
`rsvg-convert` comes from `brew install librsvg` (or `apt install librsvg2-bin`).
