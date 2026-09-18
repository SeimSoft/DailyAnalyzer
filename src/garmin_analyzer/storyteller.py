"""Gemini-powered personal diary storyteller with self-contained base64 images."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
from pathlib import Path

from google import genai
from google.genai import types

from garmin_analyzer.elevation_profile import (
    extract_elevation_points,
    generate_elevation_markdown_block,
    render_elevation_profile,
)
from garmin_analyzer.gps_map import generate_leaflet_markdown_block
from garmin_analyzer.visualizer import generate_all_interactive_plotly_blocks

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.6-flash"
FALLBACK_MODEL = "gemini-flash-latest"


def encode_image_to_base64(image_path: Path | str) -> str | None:
    """Reads an image file and returns a data URI with base64 encoded content."""
    path = Path(image_path)
    if not path.exists():
        return None

    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        ext = path.suffix.lower()
        if ext == ".png":
            mime_type = "image/png"
        elif ext in (".jpg", ".jpeg"):
            mime_type = "image/jpeg"
        elif ext == ".svg":
            mime_type = "image/svg+xml"
        elif ext == ".webp":
            mime_type = "image/webp"
        else:
            mime_type = "application/octet-stream"

    try:
        raw_bytes = path.read_bytes()
        encoded = base64.b64encode(raw_bytes).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
    except OSError as e:
        logger.warning("Failed encoding image %s to base64: %s", path, e)
        return None


def collect_day_markdowns(
    daily_dir: Path, activity_dirs: list[Path] | None = None
) -> dict[str, str]:
    """Reads all markdown files for that day: daily_summary, evaluations, activity summaries, and Garmin activity notes."""
    md_data: dict[str, str] = {}

    daily_summary_path = daily_dir / "daily_summary.md"
    if daily_summary_path.exists():
        md_data["daily_summary"] = daily_summary_path.read_text(encoding="utf-8")

    evaluations_path = daily_dir / "evaluations.md"
    if evaluations_path.exists():
        md_data["evaluations"] = evaluations_path.read_text(encoding="utf-8")

    garmin_notes_parts: list[str] = []
    elevation_parts: list[str] = []

    if activity_dirs:
        for idx, act_dir in enumerate(activity_dirs, 1):
            act_summary_path = act_dir / "activity_summary.md"
            if act_summary_path.exists():
                key = f"activity_{idx}_{act_dir.name}"
                md_data[key] = act_summary_path.read_text(encoding="utf-8")

            # Extract Garmin activity description/notes from raw_activity.json
            raw_activity_path = act_dir / "raw_activity.json"
            act_name = f"Aktivität {idx}"
            if raw_activity_path.exists():
                try:
                    raw_act = json.loads(raw_activity_path.read_text(encoding="utf-8"))
                    act_name = raw_act.get("activityName") or act_name
                    description = raw_act.get("description")
                    if description and description.strip():
                        garmin_notes_parts.append(
                            f"- **{act_name}**: {description.strip()}"
                        )
                except (json.JSONDecodeError, OSError) as err:
                    logger.debug("Could not read Garmin notes from %s: %s", raw_activity_path, err)

            # Extract elevation profile stats
            try:
                _, ele_stats = extract_elevation_points(act_dir)
                if ele_stats.get("min_elevation") is not None and ele_stats.get("max_elevation") is not None:
                    parts: list[str] = []
                    if ele_stats.get("start_elevation") is not None:
                        parts.append(f"Start: {ele_stats['start_elevation']:.0f}m")
                    parts.append(f"Höchster Punkt/Gipfel: {ele_stats['max_elevation']:.0f}m")
                    parts.append(f"Tiefster Punkt: {ele_stats['min_elevation']:.0f}m")
                    if ele_stats.get("elevation_gain"):
                        parts.append(f"Anstieg: +{ele_stats['elevation_gain']:.0f}m")
                    if ele_stats.get("elevation_loss"):
                        parts.append(f"Abstieg: -{ele_stats['elevation_loss']:.0f}m")
                    elevation_parts.append(f"- **{act_name}**: " + ", ".join(parts))
            except Exception as err:
                logger.debug("Could not extract elevation stats from %s: %s", act_dir, err)

    if garmin_notes_parts:
        md_data["garmin_activity_notes"] = (
            "## Garmin Aktivitäts-Notizen (vom Nutzer in Garmin Connect hinterlegt)\n\n"
            + "\n".join(garmin_notes_parts)
        )

    if elevation_parts:
        md_data["activity_elevation_stats"] = (
            "## Höhen- und Geländeprofile der Aktivitäten\n\n"
            + "\n".join(elevation_parts)
        )

    return md_data


def generate_diary_narrative(
    date_str: str,
    markdown_sources: dict[str, str],
    photo_paths: list[Path] | None = None,
    user_notes: str | None = None,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    """Calls Gemini with collected markdown metrics, optional user notes, and optional activity photos to generate a first-person personal diary story."""
    resolved_key = (
        api_key
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )
    if not resolved_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is missing. "
            "Please set GEMINI_API_KEY to enable LLM summary generation."
        )

    client = genai.Client(api_key=resolved_key)

    # Combine markdown sources for prompt
    sources_text = "\n\n---\n\n".join(
        f"### Source: {name}\n{content}" for name, content in markdown_sources.items()
    )

    system_instruction = (
        "Du bist ein authentischer, reflektierter und wortgewandter Mensch, der abends sein persönliches Tagebuch schreibt.\n"
        "Deine Aufgabe ist es, einen lebendigen, echten Tagebucheintrag für den heutigen Tag auf Deutsch "
        "in der ersten Person ('Ich-Form': 'Ich bin heute aufgewacht', 'Ich fühlte mich...') zu verfassen.\n\n"
        "STRIKTE REGELN ZU BIOMETRISCHEN DATEN & ZAHLEN (EXTREM WICHTIG):\n"
        "- NENNE KEINE ROHE SENSOR- ODER BIOMETRIEDATEN UND KEINE STATISTIK-ZAHLEN!\n"
        "- Niemand schreibt in ein echtes Tagebuch: 'Mein Ruhepuls lag bei 52 bpm', 'Meine HRV betrug 65 ms', "
        "'Mein Schlafscore war 82' oder 'Mein Stresslevel lag bei 35'. Das wirkt künstlich und ist STRENGSTENS UNTERSAGT!\n"
        "- Übersetze alle körperlichen Messwerte AUSSCHLIESSLICH in natürliche menschliche Empfindungen, Gefühle und Stimmungen:\n"
        "  * Schlaf: Schreibe einfach, ob du tief, erholsam und fest geschlafen hast und frisch aufgewacht bist, oder ob die Nacht unruhig, zäh war und du wie gerädert aus dem Bett gestiegen bist. Punkt.\n"
        "  * Stress & Belastung: Wenn viel Stress gemessen wurde, nenne keine Zahlen, sondern sage einfach, dass der Tag fordernd, hektisch oder nervenaufreibend war und du unter Strom standst – oder umgekehrt, dass es ein herrlich gelassener, ruhiger Tag war.\n"
        "  * Energie / Akku: Beschreibe, ob du voller Energie und Tatendrang durch den Tag gegangen bist oder ob die Batterien am Nachmittag/Abend komplett leer waren.\n"
        "  * Sport & Aktivitäten: Erzähle von der Aktivität aus dem subjektiven Erleben (die Landschaft, das Wetter, das Gefühl in den Beinen, die Anstrengung am Berg, der Atem, das Glücksgefühl) – verfasse KEINE technischen Analysen oder Datenlisten.\n\n"
        "STIL, TITEL & FORM:\n"
        "- Schreibe ausnahmslos auf Deutsch in der Ich-Form.\n"
        "- Beginne zwingend in der ALLERERSTEN Zeile mit einer kreativen, bildhaften Markdown-H1-Überschrift (# <Titel>), die das prägendste Ereignis, die Stimmung oder den besonderen Anlass des Tages aufgreift (z.B. '# 🧗 Fels, Nebel und Gipfelglück: Klettersteig am Dachstein' oder '# 🎂 Ein unvergesslicher Geburtstag auf den Spuren der Berge'). Verwende NIEMALS einfallslos 'Tagebucheintrag: <datum>' oder 'Mein Tag'!\n"
        "- Direkt unter dem H1-Titel folgt eine dezente Datumszeile in Kursivschrift (z.B. '*Montag, 24. August 2026*') und danach die fließende Erzählung.\n"
        "- Fließender Aufbau: Morgen & Erholung -> Tagesverlauf & Stimmung -> Die Aktivität & Natur -> Abendliche Reflexion.\n"
        "- Authentischer, runder Abschluss des Eintrags ohne abrupten Abbruch.\n"
        "- Erwähne keinesfalls, dass dies von einer KI oder anhand von Datendateien erstellt wurde.\n"
        "\nGARMIN AKTIVITÄTS-NOTIZEN:\n"
        "- Wenn in den Hintergrunddaten 'Garmin Aktivitäts-Notizen' vorhanden sind, sind dies persönliche Anmerkungen, "
        "die der Nutzer direkt bei der Aktivität in Garmin Connect hinterlegt hat.\n"
        "- Behandle diese Notizen als authentische, persönliche Kontextinformationen und flechte sie natürlich in den Tagebucheintrag ein.\n"
        "- Wenn sowohl Garmin-Notizen als auch Persönliche Zusatzinformationen (Nutzernotizen) vorhanden sind, "
        "haben die Nutzernotizen die höchste Priorität, aber die Garmin-Notizen sollen ergänzend einfließen.\n"
        "\nWANDERUNGEN & HÖHENPROFIL:\n"
        "- Wenn in den Hintergrunddaten Höhen- und Geländeprofile vorhanden sind (Start-, Gipfel- oder Maximalhöhe, überwundene Höhenmeter), "
        "erzähle packend und bildhaft von den Anstiegen, dem Erklimmen des Berges, dem Erreichen des höchsten Punktes/Aussichtspunkts und dem Abstieg. "
        "Beschreibe das körperliche Gefühl beim Steigen und die Weite der Ausblicke lebendig, anstatt bloße Zahlentabellen aufzulisten."
    )

    # Prepare multimodal content with photos if available
    image_parts: list[types.Part] = []
    if photo_paths:
        for p in photo_paths:
            if not p.exists():
                continue
            ext = p.suffix.lower()
            mime = "image/jpeg" if ext in (".jpg", ".jpeg") else ("image/png" if ext == ".png" else "image/webp")
            try:
                raw = p.read_bytes()
                image_parts.append(types.Part.from_bytes(data=raw, mime_type=mime))
            except OSError as e:
                logger.warning("Could not read image %s for Gemini: %s", p, e)

    photo_instruction = ""
    if image_parts:
        photo_instruction = (
            "\n\nWICHTIG - FOTOS:\n"
            "Ich habe dir auch Fotos meiner heutigen Aktivitäten beigefügt! "
            "Lass dich ganz besonders von diesen Bildern inspirieren: Betrachte die Felsen, "
            "das Klettern/Wandern, die Ausrüstung, die Berglandschaft, das Wetter und die Atmosphäre, "
            "und binde diese visuellen Eindrücke als lebendige persönliche Erinnerungen in deinen Text ein."
        )

    user_notes_block = ""
    if user_notes and user_notes.strip():
        user_notes_block = (
            f"\n\n🔥 PERSÖNLICHE ZUSATZINFORMATIONEN DES NUTZERS (HÖCHSTE PRIORITÄT):\n"
            f"\"{user_notes.strip()}\"\n\n"
            "WICHTIGSTE ANWEISUNG FÜR DIESEN EINTRAG:\n"
            "Diese Zusatznotiz ist das Herzstück und der emotionale Dreh- und Angelpunkt des Tages! "
            "Baue die gesamte Handlung, die Gedanken, die Stimmung und insbesondere den kreativen H1-Titel "
            "zwingend und entscheidend um dieses persönliche Ereignis bzw. diesen Kontext herum auf."
        )

    prompt = (
        f"Datum: {date_str}\n\n"
        f"{user_notes_block}\n\n"
        f"Hier sind die Hintergrunddaten dieses Tages (ACHTUNG: Nutze sie nur für dein Gespür für mein Befinden; nenne KEINE Zahlen, bpm, Millisekunden oder Scores im Text!):\n\n"
        f"{sources_text}"
        f"{photo_instruction}\n\n"
        "Bitte schreibe nun einen fesselnden, authentischen Tagebucheintrag auf Deutsch mit einem kreativen, individuellen H1-Titel in der ersten Zeile."
    )

    contents = [*image_parts, prompt]

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )
        return response.text or ""
    except Exception as e:
        logger.warning(
            "Gemini generation with %s failed (%s), attempting fallback to %s",
            model,
            e,
            FALLBACK_MODEL,
        )
        if model != FALLBACK_MODEL:
            response = client.models.generate_content(
                model=FALLBACK_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                    max_output_tokens=8192,
                ),
            )
            return response.text or ""
        raise


def assemble_self_contained_diary(
    date_str: str,
    narrative_text: str,
    daily_dir: Path,
    activity_dirs: list[Path] | None = None,
) -> str:
    """Assembles the final self-contained markdown file embedding interactive Leaflet routes, Plotly charts, and photos."""
    stripped_narrative = narrative_text.strip()
    first_line = stripped_narrative.split("\n", 1)[0] if stripped_narrative else ""

    if first_line.startswith("# "):
        # The narrative already contains a creative H1 headline
        lines: list[str] = [
            stripped_narrative,
            "",
            "---",
            "",
        ]
    else:
        # Generate an expressive fallback title
        act_names = []
        if activity_dirs:
            for act_dir in activity_dirs:
                parts = act_dir.name.split("_")
                clean_name = parts[-1].replace("-", " ").title() if len(parts) > 2 else act_dir.name
                act_names.append(clean_name)
        fallback_title = f"# 🌄 {', '.join(act_names)}" if act_names else f"# 📖 Tagebuch: {date_str}"

        lines = [
            fallback_title,
            f"*{date_str}*",
            "",
            stripped_narrative,
            "",
            "---",
            "",
        ]

    # Embed Activities: Interactive GPS Routes & Photos
    if activity_dirs:
        for act_dir in activity_dirs:
            gpx_file = act_dir / "track.gpx"
            gps_map_file = act_dir / "gps_map.png"
            photos_dir = act_dir / "photos"
            raw_details_file = act_dir / "raw_details.json"
            act_name = act_dir.name.replace("_", " ").title()

            # 1. Interactive Route Map via Leaflet / OpenStreetMap
            dist_km = None
            elev_m = None
            if raw_details_file.exists():
                try:
                    rd = json.loads(raw_details_file.read_text(encoding="utf-8"))
                    dist_m = rd.get("distance") or rd.get("summaryDTO", {}).get("distance")
                    if dist_m:
                        dist_km = dist_m / 1000.0
                    elev_m = rd.get("elevationGain") or rd.get("summaryDTO", {}).get("elevationGain")
                except Exception:
                    pass

            leaflet_rendered = False
            if gpx_file.exists():
                leaflet_block = generate_leaflet_markdown_block(
                    gpx_file, title=act_name, distance_km=dist_km, elevation_gain_m=elev_m
                )
                if leaflet_block:
                    lines.extend(
                        [
                            f"## 🗺️ GPS Route: {act_name}",
                            "",
                            leaflet_block,
                            "",
                        ]
                    )
                    leaflet_rendered = True

            # Fallback static image if no interactive GPX track available
            if not leaflet_rendered and gps_map_file.exists():
                b64_map = encode_image_to_base64(gps_map_file)
                if b64_map:
                    lines.extend(
                        [
                            f"## 🗺️ GPS Route: {act_name}",
                            "",
                            f"![Route Map for {act_name}]({b64_map})",
                            "",
                        ]
                    )

            # 2. Elevation Profile: Interactive Plotly Chart & Static Image Fallback
            elevation_file = act_dir / "elevation_profile.png"
            if not elevation_file.exists():
                try:
                    render_elevation_profile(
                        act_dir,
                        elevation_file,
                        title=f"Höhenprofil: {act_name}",
                        distance_km=dist_km,
                        elevation_gain_m=elev_m,
                    )
                except Exception as err:
                    logger.debug("Could not render elevation profile for %s: %s", act_dir, err)

            plotly_elevation_block = generate_elevation_markdown_block(act_dir, title=f"Höhenprofil: {act_name}")
            b64_elevation = encode_image_to_base64(elevation_file) if elevation_file.exists() else None

            if plotly_elevation_block or b64_elevation:
                lines.extend(
                    [
                        f"## ⛰️ Höhenprofil: {act_name}",
                        "",
                    ]
                )
                if plotly_elevation_block:
                    lines.extend([plotly_elevation_block, ""])
                if b64_elevation:
                    lines.extend([f"![Höhenprofil für {act_name}]({b64_elevation})", ""])

            # Photos attached to activity
            if photos_dir.exists():
                photo_files = sorted(
                    [
                        p
                        for p in photos_dir.iterdir()
                        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                    ]
                )
                if photo_files:
                    lines.extend(
                        [
                            f"## 📸 Fotos: {act_name}",
                            "",
                        ]
                    )
                    for idx, pf in enumerate(photo_files, 1):
                        b64_photo = encode_image_to_base64(pf)
                        if b64_photo:
                            lines.extend(
                                [
                                    f"![Foto {idx}]({b64_photo})",
                                    "",
                                ]
                            )

    # Embed Daily Biometrics: Interactive Plotly Charts (or fallback static images)
    raw_daily_file = daily_dir / "raw_daily.json"
    plotly_rendered = False

    if raw_daily_file.exists():
        try:
            raw_daily_data = json.loads(raw_daily_file.read_text(encoding="utf-8"))
            plotly_blocks = generate_all_interactive_plotly_blocks(raw_daily_data)

            if plotly_blocks:
                if "summary_biometrics" in plotly_blocks:
                    lines.extend(
                        [
                            "## 📈 Biometrische Tageswerte & Erholung",
                            "",
                            "*(Hinweis: Für dieses Datum liegen in Garmin Connect aggregierte Tageswerte vor; hochauflösende 24h-Minutenkurven wurden vom Server archiviert).* ",
                            "",
                            "### 📊 Tageswerte vs. 7-Tage-Vergleich",
                            "",
                            plotly_blocks["summary_biometrics"],
                            "",
                        ]
                    )
                else:
                    lines.extend(
                        [
                            "## 📈 Biometrische Tagesverläufe",
                            "",
                        ]
                    )
                    plotly_titles = [
                        ("heart_rate", "### Herzfrequenz im Tagesverlauf"),
                        ("stress", "### Stresslevel im Tagesverlauf"),
                        ("body_battery", "### Body Battery Energieverlauf"),
                        ("hrv", "### Nächtlicher HRV-Index"),
                    ]
                    for key, section_title in plotly_titles:
                        if key in plotly_blocks:
                            lines.extend(
                                [
                                    section_title,
                                    "",
                                    plotly_blocks[key],
                                    "",
                                ]
                            )
                plotly_rendered = True
        except Exception as e:
            logger.warning("Could not generate interactive Plotly charts: %s", e)

    # Fallback to static chart images if Plotly was not generated
    if not plotly_rendered:
        charts_dir = daily_dir / "charts"
        if charts_dir.exists():
            chart_configs = [
                ("heart_rate_vs_time.png", "Herzfrequenz im Tagesverlauf (24h)"),
                ("stress_vs_time.png", "Stresslevel im Tagesverlauf"),
                ("body_battery_vs_time.png", "Body Battery Lade- & Entladekurve"),
                ("hrv_vs_time.png", "Nächtlicher HRV-Index"),
            ]
            available_charts = [c for c in chart_configs if (charts_dir / c[0]).exists()]
            if available_charts:
                lines.extend(
                    [
                        "## 📈 Biometrische Tagesverläufe",
                        "",
                    ]
                )
                for filename, title in available_charts:
                    chart_file = charts_dir / filename
                    b64_chart = encode_image_to_base64(chart_file)
                    if b64_chart:
                        lines.extend(
                            [
                                f"### {title}",
                                "",
                                f"![{title}]({b64_chart})",
                                "",
                            ]
                        )

    return "\n".join(lines)


def generate_self_contained_daily_story(
    date_str: str,
    daily_dir: Path,
    activity_dirs: list[Path] | None = None,
    photo_paths: list[Path] | None = None,
    user_notes: str | None = None,
    api_key: str | None = None,
) -> tuple[Path, str]:
    """Coordinates reading markdown sources, querying Gemini, embedding base64 images, and saving daily_story.md."""
    logger.info("Generating Gemini diary story for %s...", date_str)
    md_sources = collect_day_markdowns(daily_dir, activity_dirs)
    if not md_sources:
        raise ValueError(f"No markdown source files found in {daily_dir} to summarize.")

    all_photos: list[Path] = list(photo_paths or [])
    if not all_photos and activity_dirs:
        for act_dir in activity_dirs:
            photos_dir = act_dir / "photos"
            if photos_dir.exists():
                all_photos.extend(
                    sorted(
                        [
                            p
                            for p in photos_dir.iterdir()
                            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                        ]
                    )
                )

    narrative = generate_diary_narrative(
        date_str,
        md_sources,
        photo_paths=all_photos,
        user_notes=user_notes,
        api_key=api_key,
    )
    full_markdown = assemble_self_contained_diary(
        date_str, narrative, daily_dir, activity_dirs=activity_dirs
    )

    out_file = daily_dir / "daily_story.md"
    out_file.write_text(full_markdown, encoding="utf-8")
    logger.info("Saved self-contained daily diary to %s (%d bytes)", out_file, len(full_markdown))
    return out_file, full_markdown
