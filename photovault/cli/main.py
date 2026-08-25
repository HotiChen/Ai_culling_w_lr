"""``photovault`` command-line interface.

    photovault learn <catalog-folder> --name <profile>   # stage A
    photovault inspect --name <profile>                   # show a profile
    photovault apply <photo-folder> --name <profile>      # stage B (M3)
    photovault doctor                                     # check local Gemma
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from photovault.core.learn import learn_from_folder
from photovault.core.profile import load_profile, profile_exists
from photovault.core.score import apply_to_folder
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
    typer.echo(f"  skipped     : {report.n_skipped}")
    typer.echo(f"  rule-book   : {'Gemma-generated' if report.llm_used else 'placeholder'}")
    if report.llm_note:
        typer.secho(f"  note        : {report.llm_note}", fg=typer.colors.YELLOW)
    for line in report.log:
        typer.secho(f"  log         : {line}", fg=typer.colors.YELLOW)


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
    name: str = typer.Option(..., "--name", "-n", help="Profile to score with"),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Skip Gemma gray-zone arbitration; maybe items stay as maybe"
    ),
    report: bool = typer.Option(
        True, "--report/--no-report", help="Write an HTML review report"
    ),
    sort: bool = typer.Option(
        False, "--sort/--no-sort", help="Copy photos into keep/maybe/reject subfolders"
    ),
) -> None:
    """Stage B: score a new photo folder using a learned profile (M3)."""
    settings = get_settings()
    if not profile_exists(settings.profiles_dir, name):
        typer.secho(f"profile '{name}' not found", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    sort_dir = (photo_folder / "sorted") if sort else None
    result = apply_to_folder(
        photo_folder, name, settings, report=report, sort_dir=sort_dir,
        no_llm=no_llm,
    )

    typer.secho(f"\n✓ Applied profile '{name}'", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  images     : {result.n_images}")
    typer.echo(f"  keep       : {result.n_keep}")
    typer.echo(f"  maybe      : {result.n_maybe}")
    typer.echo(f"  reject     : {result.n_reject}")
    typer.echo(f"  arbitrated : {result.n_arbitrated}")
    if result.report_path:
        typer.echo(f"  report     : {result.report_path}")
    if result.sorted_dir:
        typer.echo(f"  sorted     : {result.sorted_dir}")
    for note in result.notes:
        typer.secho(f"  note       : {note}", fg=typer.colors.YELLOW)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8000, "--port", help="Port to listen on"),
) -> None:
    """Launch the local web UI (M5). Requires the ``web`` extra.

    Lazily imports FastAPI / uvicorn so the rest of the CLI works without them.
    """
    try:
        import uvicorn  # noqa: F401
    except ImportError:  # pragma: no cover - exercised only without the extra
        typer.secho(
            "the web UI needs the 'web' extra: pip install 'photovault[web]'",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    from photovault.api.app import create_app

    settings = get_settings()
    application = create_app(settings=settings)
    typer.secho(
        f"\n✓ PhotoVault web UI on http://{host}:{port}", fg=typer.colors.GREEN, bold=True
    )
    uvicorn.run(application, host=host, port=port)


@app.command()
def doctor() -> None:
    """Check that the local Gemma server is up and has the configured model.

    A wrong model tag otherwise shows up only as a placeholder ``profile.md``,
    so this makes the failure explicit — and exits non-zero for scripting.
    """
    from photovault.core.judge import GemmaJudge

    cfg = get_settings().llm
    typer.secho("\nPhotoVault LLM check", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  backend : {cfg.backend}")
    typer.echo(f"  host    : {cfg.host}")
    typer.echo(f"  model   : {cfg.model}")

    st = GemmaJudge(cfg).status()
    if st.ok:
        typer.secho(f"  status  : ready — {st.detail}", fg=typer.colors.GREEN, bold=True)
        return

    typer.secho(f"  status  : unavailable — {st.detail}", fg=typer.colors.RED)
    typer.secho(
        "  culling still works without an LLM: add --no-llm "
        "(gray-zone photos stay as 'maybe').",
        fg=typer.colors.YELLOW,
    )
    raise typer.Exit(code=1)


def main() -> None:  # pragma: no cover - console-script entrypoint
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
