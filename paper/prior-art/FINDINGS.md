# Consolidated findings — featuretree: B-rep → verified editable feature tree

**Date:** 2026-09-19 · **Status:** all four cells complete (classical AFR, interoperability flank,
commercial/FTO, patents) + OpenAlex citation-graph traversal over 11 seeds (527 citing works,
50 citing 2+ seeds).

**Not legal advice.** This is a literature and patent *scan*, not a freedom-to-operate opinion.
Any commercial decision needs a patent attorney.

---

## 1. Executive verdict

**Do not file. Do not publish as a novelty claim. DO publish as a tools/experience paper, and do ship.**

The *method* is thoroughly anticipated — by 1995 in the academic literature, by 1998 in shipping
product, and by 2000 in (now-expired) patents. There is no defensible novelty in "recover a feature
tree from a B-rep and check it reconstructs the input."

**The dominant risk is FTO, not novelty** — novelty is simply gone. FTO is provisionally clear: no
in-force patent's independent claims read on the tool as it currently behaves, but that rests on
element-by-element non-infringement with two identified live triggers (§4), not on white space.

**What is genuinely defensible is an availability and honesty argument, not a method argument** —
and that argument is supported by a real hole in the literature (§3.1).

---

## 2. What is definitively closed

Stop claiming these. Each row carries the reference that kills it.

| Claim | Killed by |
|---|---|
| Accept a recovered feature set by re-executing it and comparing to the input | **Gupta & Nau, *CAD* 27(5), 1995** — defines an FBM as correct iff `S − ∪ rem(f) = P`. The gate, as a *definition*, 31 years ago. Rule-based, training-free. |
| Return a per-part verdict rather than a feature list | **Gupta & Nau 1995** — "If no operation plan can be found … the given design is considered unmachinable"; tolerance checker returns `failure`. |
| Reject invalid candidate features; iterate to a complete decomposition | **Vandenbrande & Requicha, *IEEE TPAMI* 15(12), 1993** — validity tests + completeness termination. |
| Geometric equivalence (not intent) as the acceptance criterion | **Willis et al., Fusion 360 Gallery, SIGGRAPH 2021** — exact reconstruction = IoU 1; a recovered sequence need not match ground truth. |
| A neutral, tool-agnostic feature IR | **Mun/Han/Kim macro-parametric approach, *CAD* 35(13), 2003**; commercially **Proficiency UPR** (Rappoport, ACM SPM 2003) — a neutral representation holding both parametric and B-rep versions of each feature. |
| One neutral IR → native editable trees in *multiple* production CAD systems | **Proficiency UPR, ~2000–2005** — shipped into CATIA V5, NX, Creo, SolidWorks, Solid Edge, Inventor. **BYU NPCF/NPDB, 2015–2018** — NX + CATIA + Creo. |
| Round-tripping human GUI edits back into the neutral representation | **Shumway, Sadler & Salmon, *CAD&A* 15(1), 2018** — "edits were made to each feature and propagated across all clients"; edits captured per-CAD and written back to the neutral DB. |
| Symbolic *query*-based references instead of persistent kernel IDs | **Cascaval, Bodík & Schulz, PLDI 2023** — "references, which are queries that select elements from the constructed geometry"; a DSL exposing queries as first-class. Also **STEP/Rappoport 2005–06** in geometric re-matching form. |
| Recover a feature tree from an imported B-rep, in product | **SolidWorks FeatureWorks (~1998)**, **PTC Creo FRT (~2007)** — the latter verbatim: *"Feature Recognition validates the model to ensure that the new features do not modify its geometry."* |
| Recover a tree + verify by deviation + emit into foreign CAD | **Geomagic Design X** — LiveTransfer into 5 CAD systems + patented Accuracy Analyzer. |
| Same, as patent disclosure | **US7099803B1** (Proficiency, prio 2000, expired): compare source/target CAD properties, adjust features outside tolerance. **US7042451B2** (Geometric, prio 2002, expired): recreate the design tree "to result in a part identical to the imported part". |

**Obviousness signature present.** Every pairwise subset of {neutral IR, multi-target native
emission, round-trip of GUI edits, query-based references, reconstruction gate} is published, and
legs 1+2+4 co-occur in a single system (BYU NPCF/NPDB). Per the skill's own rule, that is the
textbook definition of an obvious combination regardless of there being no exact match.

---

## 3. What survives

### 3.1 The only claim I would defend — availability, not method

> **The capability to recover an editable, verified design feature tree from a STEP file has existed
> in the literature since 1995 and in shipping product since 1998, is standardised in ISO 10303
> AP242, and is nevertheless available in zero open-source CAD systems and zero callable libraries.
> featuretree is a working, MIT-licensed, verification-gated implementation targeting the two CAD
> systems that lack it entirely.**

Why each qualifier is load-bearing:

- *open-source / callable library* — every anticipating system (FeatureWorks, Creo FRT, Design X,
  Elysium CADfeature, ITI Proficiency) is a GUI feature inside a proprietary seat costing thousands
  per year. None exposes an API. You cannot call any of them from your own application.
- *FreeCAD and Onshape as targets* — **Onshape's own documentation** states imported files "do not
  have a feature tree in Onshape". **FreeCAD** has had feature recognition as an open request since
  2011 ([issue #5543](https://github.com/FreeCAD/FreeCAD/issues/5543),
  [tracker #336](https://tracker.freecad.org/view.php?id=336)) with maintainers stating no capacity.
  Every published multi-target system targets enterprise CAD (NX/CATIA/Creo/SolidWorks/Inventor).
- *verification-gated with a graded, measured verdict* — the classical gate is set-theoretic Boolean
  identity (Gupta & Nau) or a convergence theorem (Kim & Wilde 1992); FeatureWorks *carries* an
  unrecognised remainder but does not *measure* it. A measured VERIFIED/PARTIAL with a geometric
  residual is a thin but real delta.
- *design feature tree, not machining features over a delta volume* — the entire classical AFR line
  outputs machining features relative to an assumed **stock**, which is not a re-executable design
  history. The interop agent's searches for "parametric feature tree recovery boundary
  representation" and "CAD model quality feature tree reconstruction verification" returned
  **0 results**.

**Biggest remaining risk:** a reviewer reads it as substituting open-source targets into a known
architecture (Proficiency UPR / BYU NPCF) — i.e. an engineering port, not a contribution.
**Cheapest thing that would kill it:** finding any open-source B-rep→feature-tree recogniser. One
search was run and found none (it returned featuretree itself); this should be repeated properly
against FreeCAD addons, CadQuery/build123d ecosystems, OCCT contrib and Bricsys BIM/Mechanical.

### 3.2 A genuine hole in the literature — worth claiming

**No published root-cause analysis of why AP203 e2 / AP242 construction-history exchange was never
adopted.** Pratt & Kim (ACM SPM 2006, *fetched and read*) state plainly: *"because these are new
capabilities … there are at present no commercial STEP translators making use of them"* and *"the
development of translators for that purpose is not an easy task"* — and the standard **deliberately
sidesteps persistent naming** rather than solving it. Nobody has closed the loop since.

This is the strongest thing found in the whole scan and it directly answers "why doesn't every CAD
tool have sensible STEP import with features?" **State it carefully**: the claim rests on a 2006
statement plus twenty years of absence of evidence, not on a published post-mortem.

### 3.3 Under-occupied niches noticed along the way

- **SHARP Challenge 2023** (ICCVW) organised a benchmark for CAD history recovery and scored it by
  *point-to-step segmentation and per-point operation labels* — a labelling metric, **not** a
  reconstruction test. The community built a history-recovery benchmark and still did not gate on
  rebuilding the solid.
- Verified-reconstruction **rate with explicit refusals** is reported by nobody. AFR reports
  accuracy/mIoU/F1 on labelled synthetic data; CAD-program inference reports IoU/Chamfer/invalidity.

---

## 4. Freedom to operate (distinct from novelty)

**No in-force patent found whose independent claims read on the tool as described.** Each requires an
element not performed: *mesh* input, a *neural network*, a *pre-existing old model*, or *interactive
face selection*.

| Patent | Assignee | Status / expiry | Risk | Gating limitation that saves you |
|---|---|---|---|---|
| **USRE48498E1** | Hexagon Metrology Korea | active, ~2029 | **HIGHEST** | Bare CRM claim — the binary is the article. Requires **3D scan data** input *and* presenting an accuracy measure to a user. |
| US11100710B2 | Dassault | active, 2039 | low | Requires a **mesh**, and enumerate-combinations-then-score. |
| US11288411B2 | PTC | active, 2040 | low | Requires selecting a **pre-existing "old model"** whose references are re-resolved. |
| US9886529B2 | HCL | granted (fees unverified) | low | Every claim gated on **interactive face-pick + highlight**. |
| US20230418990A1 | Dassault | **PENDING** | **WATCH** | Claims "optimal sequence of CAD features … optimal surface covering" from a discrete representation. Pending claims can be amended toward a competitor. |
| US11210866 / US11436795 | Dassault | active | none now | Require a **neural network** / training dataset. |
| US7643027B2 | DS SolidWorks | active to 2027-12 | negligible | Requires an existing feature collection to reorder. |

**Two live triggers for cadsketch specifically:**
1. **If the app ever ingests a LiDAR/photogrammetry scan and shows the user a deviation readout**,
   USRE48498E1 needs a proper claim read before that build ships. This is a plausible roadmap item
   for an iOS CAD app, not a hypothetical.
2. `roundtrip.py` reads edits back against a previously-recovered model — closer to PTC US11288411's
   "old model" limitation than a cold import is.

**Favourable:** FeatureWorks and Creo FRT are old enough that their patents are expired or near — free
to practise, fatal as novelty art, and strong invalidating art against anything Autodesk might file
on AutoTimeline.

**Author's own filing position:** public MIT repo since **2026-06-26**. US grace runs to
**~2027-06-26 (~9 months)**. **EPO/JP/CN/KR apply absolute novelty — those rights are already gone.**

---

## 5. Verification debt

Ranked by how much it could change the conclusions.

1. **All three independent patent legal-status services (Espacenet, Patentscope, Justia) were
   403-blocked.** Every expiry and maintenance-fee figure rests on Google Patents alone, which is
   explicitly non-authoritative. Confirm in USPTO Patent Center: USRE48498E1, US11100710B2,
   US20230418990A1, US9886529B2, US7643027B2.
2. **No JP/KR/CN-language patent sweep was run at all.** Elysium (JP) is the most on-point commercial
   product and has **zero claim-level coverage**; Rapidform's original parent INUS Technology is
   Korean, so a KR family is plausible.
3. **Pan et al., *Eng. Appl. of AI*, July 2026** — "reconstructing feature-based models from boundary
   representations". Exact input/output pair, published one month after the repo went public.
   Elsevier-paywalled; neither Crossref nor OpenAlex carries an abstract. **Title/authors/venue
   confirmed; contents unread.** Single most important unread document.
4. **Farjana & Han 2018** persistent-naming review (ScienceDirect 403) — the field's own survey; most
   likely to contain a query-based scheme not yet named.
5. Sakurai 1995/1996, Woo & Sakurai 2002, Kim 1992, Waco & Kim 1994 — all ScienceDirect-403 or
   abstract-absent. These would settle whether classical volume decomposition reports a per-instance
   verification. One candidate gap rests partly on a blocked Semantic Scholar query.
6. Cascaval 2023 (ACM DL 403) — read only at abstract level, but the abstract is decisive on its own.

**Infrastructure summary:** blocked fractions were 13%, 16%, 28% and ~7% of scholarly queries across
the four cells — but **publisher full-text fetches failed ~50%**, and **Semantic Scholar returned
HTTP 429 on 100% of attempts in two independent cells**. Nothing in this report is reported as
"no results" on the basis of a blocked query; every such case is marked.

---

## 6. Ranked next actions

1. **Reposition the paper** from novelty to availability + honest evaluation (§3.1, §3.2). This is
   the whole decision.
2. **Do not file.** ~9 months of US grace on a thin surface; ex-US already lost.
3. **Before any scan-input feature in cadsketch**, get a claim-level read on USRE48498E1.
4. **Docket US20230418990A1** (Dassault, pending) for periodic re-check.
5. Run the one search that could still kill §3.1: an exhaustive sweep for any open-source
   B-rep→feature-tree recogniser.
6. Get Pan et al. 2026 read by someone with Elsevier access.
7. If a filing is ever seriously contemplated, commission a **professional** search — amateur sweeps
   cannot support a filing decision.

---

## 7. Decisions taken (2026-09-19)

Recorded so later readers know which items were considered and consciously set aside.

- **Patent risk accepted for the open-source implementation.** Author's decision. Patents apply
  regardless of licence, so MIT is not itself a defence — but a no-revenue MIT project is not a
  realistic enforcement target. **The live exposure is `punkfab/cadsketch` shipping commercially with
  this code inside it**, and that only becomes material on the two triggers in §4 (scan input +
  user-facing deviation readout → USRE48498E1; mesh input → US11100710B2). Those remain worth a
  claim-level read *before* either feature ships, independently of the OSS position.
- **3MF pursued separately, as an interchange/carrier format, not as a recognition input.**
  3MF Core §2.1.5 permits custom OPC parts held by a MustPreserve relationship, so a `.3mf` can carry
  `/Metadata/featuretree.ir.json` beside the printable mesh — printable anywhere, still editable.
  3MF core geometry is **triangle mesh only** (no B-rep), so mesh *recognition* is a different and
  harder pipeline, and it would supply the one element currently keeping the tool outside
  US11100710B2's claims. Scope split accordingly. This direction was **not scanned** — absence of
  findings here is not evidence of novelty.

## 8. Patent addendum (second pass)

- **USRE48498E1** — assignee chain confirmed on-document: INUS Technology → 3D Systems Korea →
  **Hexagon Metrology Korea LLC**. Claim 1 verbatim requires *"a collection of 3D scan data"*,
  an operation *"other than to form the at least one CAD part body from the 3D scan data"*, and
  *"present the measure of the loss of accuracy to a user."* Bare CRM claim — the binary is the
  article. Three limitations hold it off; two are one product decision away.
- **"LiveTransfer" — no US patent found.** Eight queries across Rapidform / INUS / 3D Systems /
  3D Systems Korea / Hexagon, with Google Patents fully responsive (zero 503s all session), so this
  is a **genuine null, not a block**. Caveats: a KR family is plausible and was not reached (KIPO
  unreachable); Hexagon's "patented" marketing may simply refer to RE48498. The mechanism is
  anticipated regardless by expired **US7099803B1** claim 1 (drive the target CAD via its API, fall
  back to user emulation).
- **US9886529B2** (HCL, to 2036) — **claim 13** is the only independent claim that arguably omits the
  interactive face-pick: a headless routine listing faces, finding per-feature boundary edges, and
  flagging a shared edge. That is the one to read against the actual face-grouping code.
- **US7492364B2** (Imagecom, prio 2002, **expired** 2023) — claim 1 covers building and storing
  features "in an application neutral format" comprising feature geometry, constraints and
  dimensions. Further novelty art against a neutral-feature-IR claim; no FTO risk.
- **INUS dead filings**, useful as novelty art: US20130018634A1 (extract sweep/extrude/revolve from
  atypical digital data, abandoned), US20070285425A1 (abandoned), CN100541481C (expired 2025).
