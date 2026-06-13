"""``photovault`` command-line interface.

    photovault learn <catalog-folder> --name <profile>   # stage A
    photovault inspect --name <profile>                   # show a profile
    photovault apply <photo-folder> --name <profile>      # stage B (M3)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from photovault.core.learn import learn_from_folder
from photovault.core.profile import load_profile, profile_exists
from photovault.settings import get_settings

app = typer.Typer(
    add_completion=False,
    help="Local, offline personalized photo culling that learns your eye.",
)


@app.command()
def learn(
    catalog_folder: Path = typer.Argument(
        ..., exists=True, file_okay=False, help="Folder containing .lrcat catalogs"
    ),
    name: str = typer.Option(..., "--name", "-n", help="Profile name to create"),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Skip Gemma rule-book generation"
    ),
) -> None:
    """Stage A: learn a Taste Profile from Lightroom catalogs."""
    settings = get_settings()
    report = learn_from_folder(
        catalog_folder, name, settings, use_llm=not no_llm
    )

    typer.secho(f"\n✓ Learned profile '{report.name}'", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  saved to    : {report.profile_dir}")
    typer.echo(f"  catalogs    : {report.n_catalogs}")
    typer.echo(f"  images      : {report.n_images}")
    typer.echo(f"  keepers     : {report.n_keepers}")
    typer.echo(f"  rejects     : {report.n_rejects}")
    typer.echo(f"  presets     : {report.n_presets}")
    typer.echo(f"  rule-book   : {'Gemma-generated' if report.llm_used else 'placeholder'}")
    if report.llm_note:
        typer.secho(f"  note        : {report.llm_note}", fg=typer.colors.YELLOW)


@app.command()
def inspect(
    name: str = typer.Option(..., "--name", "-n", help="Profile name to inspect"),
) -> None:
    """Show a learned profile's metadata, thresholds and presets."""
    settings = get_settings()
    if not profile_exists(settings.profiles_dir, name):
        typer.secho(f"profile '{name}' not found", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    prof = load_profile(settings.profiles_dir, name)
    m, t = prof.meta, prof.thresholds
    typer.secho(f"\nProfile: {m.name}  (v{m.version})", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  created   : {m.created_at}")
    typer.echo(f"  images    : {m.n_images}  (keep {m.n_keepers} / reject {m.n_rejects})")
    typer.echo(f"  keep_rate : {t.keep_rate}")
    typer.echo(f"  aperture  : {t.aperture_f}")
    typer.echo(f"  iso       : {t.iso}")
    typer.echo(f"  focal     : {t.focal_length}")
    typer.echo(f"  burst keep_rate / position : {t.burst_keep_rate} / {t.keep_position_mean}")
    typer.echo(f"  presets   : {[p.stem for p in prof.preset_files]}")


@app.command()
def apply(
    photo_folder: Path = typer.Argument(..., exists=True, file_okay=False),
    name: str = typer.Option(..., "--name", "-n"),
    no_llm: bool = typer.Option(False, "--no-llm"),
) -> None:
    """Stage B: score a new photo folder using a profile. (Implemented in M3.)"""
    _ = (photo_folder, name, no_llm)
    typer.secho(
        "`apply` (stage B scoring) lands in milestone M3 — not yet implemented.",
        fg=typer.colors.YELLOW,
    )
    raise typer.Exit(code=2)


def main() -> None:  # pragma: no cover - console-script entrypoint
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
