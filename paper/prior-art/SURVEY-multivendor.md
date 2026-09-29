# Related-work survey: the featuretree IR spec and multi-backend paper

**Date:** 2026-09-29. **Purpose:** related work for a paper that publishes the featuretree IR and its
performance across CAD backends. This is a survey, not a novelty scan. The novelty and FTO questions
for recovery were settled in `FINDINGS.md` (2026-09-19); this file adds three cells on top of it.
BibTeX for everything new is in `survey/references-multivendor.bib`, each entry marked with how it
was verified.

---

## 1. Verdict

The paper is publishable as a spec-and-measurement paper. It is not publishable as a "first".

- **The closest work is CADIR** (Liu, Ni, Chen, Huang, Tong, Tang, Du; arXiv 2608.00891, v1
  2026-08-01, read in full). It is an agent-facing executable IR on OCCT/OCP with 115 operations. It
  records a construction graph, and adapters rebuild *native editable feature histories in FreeCAD,
  SolidWorks and Fusion 360*. It reports per-backend IoU (0.937 / 0.945 / 0.976 as extracted by the
  survey agent; recheck against the PDF before quoting) and an edit-success rate. Code:
  github.com/NiJingzhe/SimpleCADAPI (Apache-2.0).
- **The macro-parametric line** (Mun/Han 2003; Proficiency UPR; BYU NPCF; Safdar 2020) already did
  neutral-IR to multi-commercial-CAD exchange through vendor APIs, and named its hard problems:
  feature mapping, persistent naming and constraint translation.
- So "one IR emitted as native trees into several CAD systems" is established twice over, in 2003
  and again in 2026. The paper should present featuretree as an independent, parallel point in that
  design space. For the record: featuretree's repo was public 2026-06-26 and its recogniser commits
  date to 2026-07-10, before CADIR v1. State those dates plainly and make no priority claim beyond them.

## 2. What differs, and so what the paper can claim

| featuretree | Nearest precedent | Difference |
|---|---|---|
| Declarative, non-Turing-complete JSON feature list; the spec is the artifact | CADIR (Python SDK over OCP); code-CAD (CadQuery, build123d, FeatureScript, KCL); ML formats (DeepCAD tokens, CadQuery-as-IR in CAD-Recode) | A data format any tool can emit or consume without a Python runtime. Wider than the ML sketch-extrude formats (fillet, taper, revolve, polar pattern, sketch-on-face, arbitrary-plane cuts); far narrower than code-CAD |
| References are stored *queries* re-resolved on every build (`face_of`+`side`, `circles: top_outer`) | Capoyleas/Chen/Hoffmann 1996 generic naming; Wang & Nnaji 2005 geometry-based semantic IDs; Bidarra & Bronsvoort 2002; CadQuery/build123d selectors; FeatureScript `qCreatedBy`; Cascaval PLDI 2023; CADIR's Geometric Signature Matching | featuretree stores the query itself. CADIR records the selected topology and re-matches it by signature; Kripac 1997 / OCAF / FreeCAD 1.0 track names through history. The known cost has to be stated: a query can resolve to a different entity after an edit |
| Backends include Onshape and build123d as well as FreeCAD; Fusion and SolidWorks as generated scripts | CADIR: FreeCAD, SolidWorks, Fusion. Makatura 2023 and CADFS (CVPR 2026): Onshape only | No surveyed system targets Onshape together with other systems |
| The same IR is the target of a STEP → feature-tree recogniser | CADIR, and the LLM-CAD line, generate forward only | Recognition and forward emission share one representation |
| Verification: Boolean-free IoU ≥ 99.5% + volume ≤ 0.5%, a per-feature volume trace locating the first divergent feature, and native files read back by two independent decoders | CAx-IF geometric validation properties (volume/area/centroid, green < 1%); Sap & Shapiro 2019 / Sap & Szabo 2025 invariant-property interop testing; IoU in CADIR, CAD-Recode, LLM4CAD; McKeeman 1998 differential testing | Each part has precedent. The combination, applied to feature-tree emission, is the measurement contribution. **The NIST result** (Onshape 11/11, cadmpeg 1/11, 4 silent failures) is a differential-testing finding with no precedent found for CAD decoders. That absence is weak evidence, from a few queries only |

## 3. Claims to avoid

- "First to emit one IR as native feature trees in several CAD systems." Mun/Han 2003, Proficiency, BYU, and CADIR 2026.
- "Query-based references are new." Capoyleas 1996, Wang & Nnaji 2005, Cascaval 2023, and every code-CAD selector system.
- "A volume check verifies interoperability." CAx-IF validation properties and Sap & Shapiro 2019 are the precedent; cite them. Also answer the obvious reviewer question: CAx-IF also checks area and centroid, which we don't. IoU catches misplacement that volume alone would miss.
- "Boolean-free IoU is novel." It is point-membership classification (Tilove 1980). Justify the Boolean-free choice with the robustness literature (Kettner 2008; Zhou 2016) and our own observation on NIST parts.
- Anything about Fusion or SolidWorks *results* before they have actually run.

## 4. Related-work outline for the paper

1. **Neutral feature-history exchange.** ISO 10303-55/108/111/112 (Pratt & Kim 2006; Kim et al. 2008; Kim et al. 2011 for -112); macro-parametric (Mun/Han 2003; Safdar 2020; Kim 2019 assemblies); Proficiency UPR; BYU NPCF/NPDB (Shumway 2018). Economic motivation: Brunnermeier & Martin 2002.
2. **CAD as a language.** Code-CAD (OpenSCAD, CadQuery, build123d, FeatureScript, KCL — grey literature; Machado 2019 as the academic anchor); PL views (Nandi 2018, Szalinski 2020, Cascaval 2023; Ritchie 2023 survey).
3. **Learned construction sequences as de-facto IRs.** SketchGraphs, DeepCAD, SkexGen, Fusion 360 Gallery, Text2CAD, CAD-Recode: mostly sketch+extrude, quantized tokens or CadQuery.
4. **Persistent naming.** Capoyleas 1996, Kripac 1997, Marcheix & Pierra 2002 (survey), Bidarra & Bronsvoort 2000/2002, Wang & Nnaji 2005, Farjana & Han 2018 (review); OCAF TNaming; FreeCAD 1.0 TNP mitigation.
5. **LLM and agent CAD generation.** CADIR (closest); CADFS and Makatura (Onshape); CADCodeVerify, CAD-Coder, Zero-to-CAD (CadQuery); Query2CAD, CAD-Assistant, Hepworth & Gauch 2026 (FreeCAD); LLM4CAD; vendor MCP servers (grey literature).
6. **Measuring exchange quality.** CAx-IF validation properties; ISO 10303-59 / PDQ (Kikuchi 2010); Gerbino & Brondi 2004 benchmark; Hoffmann/Shapiro/Srinivasan 2014, Sap & Shapiro 2019, Sap & Szabo 2025; González-Lluch 2017 survey; NIST PMI test system (Lipman & Filliben 2017, 2020; Cheney & Fischer 2015; Lipman & Lubell 2015).
7. **Metrics and oracles.** Point-membership classification (Tilove 1980; Requicha 1980); Hausdorff (Huttenlocher 1993); robustness failures (Kettner 2008; Zhou 2016); differential testing and the oracle problem (McKeeman 1998; Csmith 2011; Barr 2015; Donaldson 2017; Spatter 2024).

## 5. Verification debt (check before submission)

- **CADIR:** read the PDF itself for the IoU numbers, the benchmark, and whether its adapters were run in real SolidWorks and Fusion.
- **Metadata only.** Every item in cells 1 and 3 marked ABSTRACT-LEVEL or VERIFIED-METADATA is metadata or abstract only. Representation details (DeepCAD's command set, "no fillet" in the ML formats) come from the agents' background knowledge.
- **Author lists completed by the agent from memory:** Safdar 2020 (last four authors, volume/pages), Kim 2019 first author, LLM4CAD first names, and trailing authors of Text2CAD and CAD-Assistant.
- **Unconfirmed venues:** SketchGraphs (arXiv; possibly an ICML 2020 workshop).
- **ISO editions:** ISO 10303-59 2021 vs 2022; ISO 10303-112 title from a search snippet (iso.org returned 403).
- **McKeeman 1998** pages from dblp/S2 listings seen through search (dblp was bot-gated).
- **Lee & Requicha 1982 Part I** may not cover Monte Carlo; cite Tilove for point-membership classification.
- **FreeCAD TNP credit:** cite the release notes only unless the Ondsel post is fetched.
- **Unassessed arXiv papers:** ArtiCAD 2604.10992, LLM4CAD-Editor 2606.20607, ArtisanCAD 2607.05750, CADDesigner 2508.01031 (same group as CADIR), EvoCAD 2510.11631, and the LLM-for-CAD survey 2505.08137. Skim the survey for anything else missed.

## 6. Infrastructure notes

- **Blocked or rate-limited sources.** These gaps are not evidence of absence.
  - Semantic Scholar rate-limited (429) most calls in all three cells; Crossref, OpenAlex and arXiv covered.
  - dblp was bot-gated or unreachable in all three.
  - OpenReview content was gated.
  - iso.org returned 403.
  - Elsevier withheld several abstracts.
- **No full text read in cell 1.** Cells 2 and 3 read several full texts (CAx-IF GVP 4.2, CADIR, CADFS, Zero-to-CAD, Makatura, CADCodeVerify, Query2CAD, Hepworth & Gauch).
