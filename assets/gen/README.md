# Stage flowchart generator

`stage_flows.py` draws `assets/stageN_flow.svg` from `flowgen.py`'s small
node/edge layout. Edit a stage's nodes or result lines, then regenerate:

```
cd assets/gen && python3 stage_flows.py .. && cd .. && for s in 1 2 3 4; do rsvg-convert -z 1.5 stage${s}_flow.svg -o stage${s}_flow.png; done
```
`rsvg-convert` comes from `brew install librsvg`.
