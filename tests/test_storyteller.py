"""Unit tests for Gemini diary storyteller and base64 markdown embedding."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from garmin_analyzer.storyteller import (
    assemble_self_contained_diary,
    collect_day_markdowns,
    encode_image_to_base64,
    generate_diary_narrative,
    generate_self_contained_daily_story,
)


def test_encode_image_to_base64(tmp_path: Path):
    fake_png = tmp_path / "chart.png"
    fake_png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00fake_image_data")

    data_uri = encode_image_to_base64(fake_png)
    assert data_uri is not None
    assert data_uri.startswith("data:image/png;base64,")


def test_collect_day_markdowns(tmp_path: Path):
    daily_dir = tmp_path / "daily_health" / "2026-06-16"
    daily_dir.mkdir(parents=True)
    (daily_dir / "daily_summary.md").write_text("# Daily Summary Content", encoding="utf-8")
    (daily_dir / "evaluations.md").write_text("# Evaluations Content", encoding="utf-8")

    act_dir = tmp_path / "activities" / "2026-06-16_123_run"
    act_dir.mkdir(parents=True)
    (act_dir / "activity_summary.md").write_text("# Activity Content", encoding="utf-8")

    sources = collect_day_markdowns(daily_dir, activity_dirs=[act_dir])
    assert "daily_summary" in sources
    assert "evaluations" in sources
    assert any("activity" in k for k in sources)


def test_assemble_self_contained_diary(tmp_path: Path):
    daily_dir = tmp_path / "daily_health" / "2026-06-16"
    charts_dir = daily_dir / "charts"
    charts_dir.mkdir(parents=True)
    (charts_dir / "heart_rate_vs_time.png").write_bytes(b"\x89PNGfakehr")

    act_dir = tmp_path / "activities" / "2026-06-16_123_walk"
    act_dir.mkdir(parents=True)
    (act_dir / "gps_map.png").write_bytes(b"\x89PNGfakemap")

    narrative = "I started my morning with an easy awakening and ended with a scenic walk."
    diary_md = assemble_self_contained_diary(
        "2026-06-16",
        narrative,
        daily_dir=daily_dir,
        activity_dirs=[act_dir],
    )

    assert "# 🌄 Walk" in diary_md
    assert "*2026-06-16*" in diary_md
    assert narrative in diary_md
    assert "data:image/png;base64," in diary_md
    assert "GPS Route:" in diary_md
    assert "Herzfrequenz im Tagesverlauf" in diary_md

    # Test with explicit creative H1 headline from LLM
    creative_narrative = "# 🧗 Gipfelsturm im Dachstein-Nebel\n*16. Juni 2026*\n\nEin intensiver Tag in den Bergen."
    diary_md_creative = assemble_self_contained_diary(
        "2026-06-16",
        creative_narrative,
        daily_dir=daily_dir,
        activity_dirs=[act_dir],
    )
    assert "# 🧗 Gipfelsturm im Dachstein-Nebel" in diary_md_creative
    assert "Ein intensiver Tag in den Bergen." in diary_md_creative


@patch("garmin_analyzer.storyteller.genai.Client")
def test_generate_diary_narrative_mock(mock_client_cls):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "I woke up feeling refreshed. Later I enjoyed a 5 km walk."
    mock_client.models.generate_content.return_value = mock_response
    mock_client_cls.return_value = mock_client

    result = generate_diary_narrative(
        date_str="2026-06-16",
        markdown_sources={"daily": "HR: 50 bpm"},
        api_key="fake-test-key",
    )

    assert "5 km walk" in result
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].max_output_tokens == 8192


@patch("garmin_analyzer.storyteller.genai.Client")
def test_generate_diary_narrative_with_photos(mock_client_cls, tmp_path: Path):
    fake_photo = tmp_path / "climbing.jpg"
    fake_photo.write_bytes(b"\xff\xd8\xff\xe0fake_jpeg")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Heute war ich in den Bergen klettern."
    mock_client.models.generate_content.return_value = mock_response
    mock_client_cls.return_value = mock_client

    result = generate_diary_narrative(
        date_str="2026-08-24",
        markdown_sources={"activity": "Ramsau am Dachstein Klettern"},
        photo_paths=[fake_photo],
        api_key="fake-test-key",
    )

    assert "klettern" in result
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    contents = call_kwargs["contents"]
    # There should be image Part and prompt string
    assert len(contents) >= 2
    assert call_kwargs["config"].max_output_tokens == 8192


@patch("garmin_analyzer.storyteller.genai.Client")
def test_generate_diary_narrative_with_user_notes(mock_client_cls):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "# 🎂 Mein Geburtstag am Fels\n*16. Juni 2026*\n\nEin ganz besonderer Tag."
    mock_client.models.generate_content.return_value = mock_response
    mock_client_cls.return_value = mock_client

    result = generate_diary_narrative(
        date_str="2026-06-16",
        markdown_sources={"daily": "Erholung gut"},
        user_notes="Mein 40. Geburtstag mit Familie und Freunden!",
        api_key="fake-test-key",
    )

    assert "Mein Geburtstag" in result
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    prompt_str = call_kwargs["contents"][-1]
    assert "Mein 40. Geburtstag" in prompt_str
    assert "PERSÖNLICHE ZUSATZINFORMATIONEN DES NUTZERS (HÖCHSTE PRIORITÄT)" in prompt_str
    # Verify strict no biometric numbers rule in system instruction
    sys_inst = call_kwargs["config"].system_instruction
    assert "NENNE KEINE ROHE SENSOR- ODER BIOMETRIEDATEN" in sys_inst


@patch("garmin_analyzer.storyteller.generate_diary_narrative")
def test_generate_self_contained_daily_story(mock_generate, tmp_path: Path):
    mock_generate.return_value = "Today was a balanced day."

    daily_dir = tmp_path / "daily_health" / "2026-06-16"
    daily_dir.mkdir(parents=True)
    (daily_dir / "daily_summary.md").write_text("# Summary", encoding="utf-8")

    out_file, content = generate_self_contained_daily_story(
        "2026-06-16",
        daily_dir=daily_dir,
        api_key="fake-key",
    )

    assert out_file.exists()
    assert "Today was a balanced day." in content


def test_assemble_with_interactive_leaflet_and_plotly(tmp_path: Path):
    daily_dir = tmp_path / "daily_health" / "2026-06-16"
    daily_dir.mkdir(parents=True)
    raw_daily = {
        "date": "2026-06-16",
        "heart_rates": {
            "heartRateValues": [[1718500000000, 65], [1718500120000, 72]],
            "restingHeartRate": 55,
        },
        "stress": {
            "stressValuesArray": [[1718500000000, 20], [1718500120000, 35]],
            "avgStressLevel": 28,
        },
    }
    import json
    (daily_dir / "raw_daily.json").write_text(json.dumps(raw_daily), encoding="utf-8")

    act_dir = tmp_path / "activities" / "2026-06-16_999_run"
    act_dir.mkdir(parents=True)
    gpx_content = """<?xml version="1.0" encoding="UTF-8"?>
    <gpx version="1.1" creator="Garmin"><trk><trkseg>
        <trkpt lat="47.881" lon="11.912"><ele>500</ele></trkpt>
        <trkpt lat="47.885" lon="11.918"><ele>510</ele></trkpt>
    </trkseg></trk></gpx>"""
    (act_dir / "track.gpx").write_text(gpx_content, encoding="utf-8")

    diary = assemble_self_contained_diary(
        date_str="2026-06-16",
        narrative_text="Ein wunderbarer Tag in den Bergen.",
        daily_dir=daily_dir,
        activity_dirs=[act_dir],
    )

    assert "```leaflet" in diary
    assert "```plotly" in diary
    assert "Herzfrequenz im Tagesverlauf" in diary
    assert "Stresslevel im Tagesverlauf" in diary
    assert "Ein wunderbarer Tag in den Bergen." in diary

