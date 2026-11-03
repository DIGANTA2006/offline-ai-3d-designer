# CuraEngine and Cura definition resources

The generic machine and extruder profiles in this folder are project-authored and inherit Cura's base `fdmprinter` and `fdmextruder` definitions. The two base definition files are vendored from the official Ultimaker Cura repository at immutable commit `11af2cf24d76186f1ec9d353a1cb134eea22f199` (Cura 4.13 source line) so the deployed CuraEngine 4.13 runtime can resolve the profile inheritance chain without downloading files during image build.

The corresponding upstream license text is included as [CURA-UPSTREAM-LICENSE.txt](CURA-UPSTREAM-LICENSE.txt). Preserve that license with the upstream files and any redistributed copy.

The project-authored generic profiles are defaults for software integration and smoke testing, **not a certified profile for any particular printer**. Confirm the actual printer model, firmware, build volume, start/end G-code, nozzle, extruder, filament diameter, material temperatures and bed before printing. A successful CuraEngine slice and structurally valid G-code do not establish physical print safety or successful print acceptance.

Upstream project: https://github.com/Ultimaker/Cura
