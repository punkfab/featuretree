# Zenodo deposit — paste-ready fields

Two *separate* DOIs are worth having. They are independent; do either or both.

---

## A. Preprint DOI (the arXiv substitute) — no GitHub integration needed

Go to <https://zenodo.org/uploads/new> and upload **one file**:

    paper/featuretree-paper-v0.1.0.pdf

Then fill in:

| Field | Value |
|---|---|
| **Resource type** | Publication → **Preprint** |
| **Title** | featuretree: Verified Recovery of Editable CAD Feature Trees from STEP, for Open CAD Systems |
| **Creator** | Newcome, Daniel · ORCID `0009-0000-6015-8713` · Affiliation: punkfab |
| **Publication date** | 2026-09-19 |
| **License** | Creative Commons Attribution 4.0 International (CC-BY-4.0) |
| **Version** | 0.1.0 |
| **Language** | English |

**Description** (paste as-is):

> Importing a STEP file into a parametric CAD system yields a single frozen solid: the design
> history is gone, and no pad depth or hole diameter can be edited. Recovering that history is a
> well-studied problem — the acceptance criterion used here was stated as a definition by Gupta and
> Nau in 1995, and commercial implementations have shipped since roughly 1998. It is nonetheless
> absent from every open-source CAD system and from every callable library we could find: the
> capability exists only inside proprietary seats costing thousands of dollars per year, with no API.
>
> This paper describes featuretree, an MIT-licensed, training-free recogniser that recovers an
> editable feature tree from an exact boundary representation, gates every recovery by re-executing
> the tree and comparing the result against the input, and emits into FreeCAD and Onshape — two
> systems with no import-time feature recognition at all. On the eleven-part NIST MBE PMI
> conformance corpus it returns VERIFIED for 3 parts, PARTIAL for 5, and explicitly refuses 3,
> producing no silently incorrect trees; all three VERIFIED recoveries exceed 99.68% IoU against the
> input. We also report a negative result about the acceptance criterion itself: a scalar volume
> comparison lets over-cut and uncut material cancel, understating the true geometric discrepancy by
> 1.56x on one part, which a two-sided IoU test eliminates.
>
> No methodological novelty is claimed. The contribution is an available, honest implementation and
> a measured account of where it fails.

**Keywords:** CAD; parametric modeling; feature recognition; reverse engineering; boundary
representation; STEP; ISO 10303; FreeCAD; Onshape; build123d; open source

**Related identifiers:**

| Relation | Identifier |
|---|---|
| *is supplement to* | `https://github.com/punkfab/featuretree` (URL) |

---

## B. Software DOI (archives the repository at a tag)

Requires the GitHub hook, which needs organization approval because `punkfab` is an org:

1. GitHub → Settings → Applications → **Authorized OAuth Apps** → **Zenodo**
2. Under *Organization access*, click **Grant** beside `punkfab`
   (you are an org **admin**, so this grants immediately — no request to approve)
3. <https://zenodo.org/account/settings/github/> → **Sync now**
4. Toggle `punkfab/featuretree` **ON**
5. Only then tag `v0.1.0` — Zenodo ignores releases created before the toggle was enabled

Metadata comes from `.zenodo.json` at the repo root, which is already written — title, creator with
ORCID, MIT licence, keywords and description, including the scope-of-claim note.

**Note:** Zenodo lists only repositories where you hold admin rights, and the list is cached. If
`punkfab` repos still do not appear after granting, press *Sync now* again.

---

## After either deposit

Send me the DOI and I will write it into:

- `paper/main.tex` — the Availability section (there is a `TODO-ON-DEPOSIT` marker)
- `CITATION.cff` — as `doi:` and `identifiers:`
- `README.md` — a DOI badge

Zenodo DOIs are **permanent and public**. A record cannot be deleted once published, only superseded
by a new version — which is exactly what makes it citable.
