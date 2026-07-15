# Result Extraction Component Mapping - 2026-06-18

This note fixes the reviewed S2 command-stream mapping used by CableTrayAI
after comparing the department model/post streams with generated mixed-tray
component-topology streams.

## Department Source Semantics

In the reviewed department post stream, the main stress extraction starts with:

```apdl
ESEL,S,TYPE,,1
```

For the reviewed source models, `TYPE=1` means the square support plus tray
arms. Tray beams use another element type and are not part of this main stress
selection. Therefore the reviewed `MAXBEAMSTRESS.LIS` and appendix-B `B*` /
`D*` stress figures are not tray-only and not square-only; they are the
TYPE=1-equivalent beam set: square support + tray arms, excluding trays and
bolts.

The cantilever-arm branch then narrows the source set with:

```apdl
ESEL,S,TYPE,,1
ESEL,U,SEC,,1
```

That branch is the source of `TMAXBEAMSTRESS.LIS` and the `TB*` / `TD*`
cantilever stress figures when the square tube outer width requires the
cantilever cloud branch.

## CableTrayAI Component-Topology Equivalent

For generated mixed-tray models, CableTrayAI writes explicit element
components:

| Component | Meaning | Used by |
| --- | --- | --- |
| `CTAI_SUPPORT_ELEMS` | square support only | `SQUAREBEAMSTRESS.LIS` numeric audit |
| `CTAI_ARM_ELEMS` | tray arms only | `TMAXBEAMSTRESS.LIS`, appendix-C figures |
| `CTAI_TRAY_ELEMS` | tray beams only | model display only, not main stress evaluation |
| `CTAI_BOLT_ELEMS` | bolt connector beams | bolt/load extraction only |
| `CTAI_TYPE1_ELEMS` | support + arms | semantic equivalent of department `TYPE=1` |

The production post stream must therefore use:

```apdl
CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM
CMSEL,A,CTAI_ARM_ELEMS,ELEM
```

before `MAXBEAMSTRESS-WRITE` and before the `B*` / `D*` appendix-B stress
figures.

The square-support-only numeric audit must use:

```apdl
CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM
```

and only writes `SQUAREBEAMSTRESS.LIS`. It must not generate `SQ-*` figures and
must not replace appendix-B `B*` / `D*` figures.

The cantilever-arm-only branch must use:

```apdl
CMSEL,S,CTAI_ARM_ELEMS,ELEM
```

before `TMAXBEAMSTRESS-WRITE` and the `TB*` / `TD*` figures.

## Gate Rules

1. `MAXBEAMSTRESS.LIS`: support + arms, no trays or bolts.
2. Appendix B `B*` / `D*` figures: same support + arms selection as
   `MAXBEAMSTRESS.LIS`.
3. `SQUAREBEAMSTRESS.LIS`: support only; numeric source for square-support
   deterministic evaluation.
4. No `SQ-*` figure is required or published for new production jobs.
5. `TMAXBEAMSTRESS.LIS` and `TB*` / `TD*`: arms only.
6. `TBMODEL`: model display of arms and trays is allowed, but it is not a
   stress-evaluation selector and must not be reused for numeric extraction.
