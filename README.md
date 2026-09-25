# Structured Hardening Project

The **Structured Hardening Project (SHP)** is a structured hardening standard for defining, applying, verifying, and certifying security controls against explicit platform specifications and threat models.

This repository contains the canonical SHP specification corpus and its supporting repository tooling.

## What SHP Does

SHP defines structured hardening requirements in a form intended to be:

- explicit;
- deterministic;
- verifiable;
- reproducible;
- versioned; and
- suitable for evidence-based certification.

SHP certification is based on defined controls, machine-readable evidence, deterministic verification, and governed certification decisions.

Certification is device-bound, state-bound, and time-bounded. It is not a permanent property of a device.

## What This Repository Contains

The repository includes SHP material covering areas such as:

- project governance;
- specification authority;
- tier mathematics;
- control evaluation;
- verification architecture;
- certification evidence and decision models;
- certification trust architecture;
- platform threat models;
- platform mathematics;
- tier control catalogues; and
- supporting governance and operational specifications.

The presence of a document in this repository does **not**, by itself, mean that the document is Active, authoritative for a particular decision, or currently applicable.

Likewise, the presence of material relating to a platform does **not** mean that the platform has been formally admitted for SHP certification.

Applicable governance records and specifications determine those matters.

## Repository Authority Boundary

This repository is the canonical version-controlled corpus for SHP specifications.

Git and GitHub provide storage, publication, integrity references, and historical traceability. They do **not** determine normative authority.

Normative authority is determined by the SHP governance framework, including the Structured Hardening Project Charter and Specification Authority Registry.

Repository location, directory placement, filename, commit recency, or inclusion in a source set must not be treated as a substitute for governed document status or authority.

## Source Sets

The `source-sets/` infrastructure provides deterministic working selections of repository material.

A source-set manifest binds selected repository paths and their SHA-256 digests to a specific Git commit.

Current working source sets include:

- Core;
- Fedora;
- Wi-Fi; and
- Network Gateway.

Source sets are selection and reproducibility mechanisms only.

A source set does **not**:

- activate a specification;
- confer normative authority;
- admit a platform;
- establish tier status;
- establish certification eligibility; or
- supersede SHP governance.

Those decisions remain governed by the applicable SHP specifications and records.

## Verification Tooling

Repository tooling used for source-set validation is designed to operate deterministically against the Git commit identified by a manifest.

Pinned validation reads artifact bytes from the declared Git commit tree rather than relying on the current working tree.

The source-set validator has a regression qualification suite covering commit resolution, artifact integrity, generator integrity, duplicate paths, missing artifacts, schema constraints, dirty working-tree isolation, and historical commit verification.

This tooling validates repository/source-set integrity. It does **not** itself perform SHP device certification.

## Platform Boundaries

No platform is implicitly supported by SHP.

Platform material may exist in this repository while remaining draft, historical, experimental, superseded, or otherwise outside current certification eligibility.

Formal platform support and certification eligibility must be established through the applicable SHP governance process.

## Certification Boundary

Possession of SHP specifications, use of SHP tooling, successful local verification, or reproduction of SHP controls does not constitute SHP certification.

Certification authority remains governed by SHP certification and trust architecture.

Client self-signing is not SHP certification.

## Historical Material

Historical and superseded material may be retained to preserve auditability, reproducibility, and the meaning of earlier certification states.

Do not infer current applicability merely from the continued presence of historical material.

## Project Website

Public information about the Structured Hardening Project is published separately through the SHP website.

The website is a presentation and information layer. This repository remains the canonical specification corpus.

## Licence

Licensing terms for SHP specifications and repository material must be determined by the applicable repository licence and SHP governance.

No licence is implied by this README.
