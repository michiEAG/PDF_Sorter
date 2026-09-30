# Standort-Auswertung über PDF-Koordinaten korrigiert

import streamlit as st
import fitz  # PyMuPDF
import re
import os
import shutil
import zipfile
from io import BytesIO


# ============================================================
# Streamlit-Konfiguration
# ============================================================

st.set_page_config(
    page_title="PDF Splitter",
    page_icon="📄",
    layout="centered"
)

st.title("📄 PDF Split & Benennung")
st.write("PDFs anhand eines Textfeldes automatisch trennen und benennen.")


# ============================================================
# Hilfsfunktionen
# ============================================================

def clean_filename(value):
    """
    Entfernt ungültige Zeichen aus Datei- und Ordnernamen.
    """
    value = str(value).strip()

    # Ungültige Zeichen unter Windows entfernen
    value = re.sub(r'[\\/:*?"<>|]', "_", value)

    # Zeilenumbrüche und mehrere Leerzeichen ersetzen
    value = re.sub(r"\s+", "_", value)

    # Mehrere Unterstriche reduzieren
    value = re.sub(r"_+", "_", value)

    # Unterstriche am Anfang/Ende entfernen
    value = value.strip("_")

    return value


def normalize_word(word):
    """
    Vereinheitlicht ein Wort für den Vergleich.
    Beispiel:
    'Standort:' -> 'standort'
    'Standort' -> 'standort'
    """
    word = word.strip().lower()
    word = word.replace(":", "")
    word = word.replace(";", "")
    return word


def extract_value_by_position(page, field_name):
    """
    Liest einen Feldwert anhand der Position auf der PDF-Seite aus.

    Beispiel im PDF:

        Standort:                 Dällikon

    Der Wert wird rechts neben dem Feldlabel auf derselben
    horizontalen Zeile gesucht.
    """

    words = page.get_text("words")

    # words enthält normalerweise:
    # x0, y0, x1, y1, text, block_no, line_no, word_no
    if not words:
        return None

    target = normalize_word(field_name)

    # Zuerst das Feldlabel suchen
    label_word = None

    for word in words:
        text = word[4]
        normalized = normalize_word(text)

        if normalized == target:
            label_word = word
            break

    if label_word is None:
        return None

    label_x0, label_y0, label_x1, label_y1 = label_word[:4]
    label_center_y = (label_y0 + label_y1) / 2

    # Kandidaten rechts neben dem Label auf derselben Zeile suchen
    candidates = []

    for word in words:
        x0, y0, x1, y1, text = word[:5]

        # Das Wort muss rechts vom Feldlabel stehen
        if x0 <= label_x1:
            continue

        # Dasselbe Wort bzw. reine Satzzeichen ignorieren
        if text.strip() in [":", ";", "-", "–"]:
            continue

        # Vertikale Toleranz für die gleiche Zeile
        word_center_y = (y0 + y1) / 2

        if abs(word_center_y - label_center_y) <= 5:
            candidates.append(word)

    if not candidates:
        return None

    # Das nächstgelegene Wort rechts vom Label ist der Feldwert
    candidates.sort(key=lambda item: item[0])

    value = candidates[0][4].strip()

    # Falls versehentlich ein Doppelpunkt erkannt wurde
    value = value.strip(":;,- ")

    return value if value else None


def extract_text_value(text, regex_pattern):
    """
    Extrahiert einen Feldwert aus dem normalen PDF-Text.
    """
    pattern = re.compile(regex_pattern, re.MULTILINE)
    match = pattern.search(text)

    if not match:
        return None

    return match.group(1).strip()


# ============================================================
# 1. PDF Upload
# ============================================================

uploaded_file = st.file_uploader(
    "PDF hochladen",
    type=["pdf"]
)


if uploaded_file:

    # ========================================================
    # 2. Dateiname-Präfix
    # ========================================================

    default_prefix = "2026_Geräteprüfung"

    file_prefix = st.text_input(
        "Dateiname-Präfix",
        value=default_prefix
    )


    # ========================================================
    # 3. Aufteilungskriterium
    # ========================================================

    option = st.selectbox(
        "Nach welchem Feld soll aufgeteilt werden?",
        [
            "Inventar-Nr.",
            "Beschreibung",
            "Raum-ID",
            "Standort",
            "Benutzerdefiniert"
        ]
    )


    # ========================================================
    # Feld auswählen
    # ========================================================

    regex_pattern = None
    feld_name = option

    if option == "Benutzerdefiniert":

        feld_name = st.text_input(
            "Feldbezeichnung ohne Doppelpunkt"
        )

        if not feld_name:
            st.info("Bitte eine Feldbezeichnung eingeben.")
            st.stop()

        regex_pattern = (
            rf"{re.escape(feld_name)}[ \t]*:[ \t]*([^\r\n]+)"
        )

    elif option == "Inventar-Nr.":

        regex_pattern = (
            r"Inventar-Nr\.[ \t]*:[ \t]*([^\r\n]+)"
        )

    elif option == "Beschreibung":

        regex_pattern = (
            r"Beschreibung[ \t]*:[ \t]*([^\r\n]+)"
        )

    elif option == "Raum-ID":

        regex_pattern = (
            r"Raum-ID[ \t]*:[ \t]*([^\r\n]+)"
        )

    elif option == "Standort":

        # Standort wird nicht über ein Zeilen-Regex ausgelesen.
        # Er wird anhand seiner Position auf der PDF-Seite ermittelt.
        regex_pattern = None


    # ========================================================
    # 4. PDF verarbeiten
    # ========================================================

    if st.button("🚀 PDF verarbeiten"):

        with st.spinner("PDF wird verarbeitet..."):

            # ------------------------------------------------
            # Temporäre Ordner vorbereiten
            # ------------------------------------------------

            work_dir = "work"
            output_dir = os.path.join(work_dir, "output")

            if os.path.exists(work_dir):
                shutil.rmtree(work_dir)

            os.makedirs(output_dir)


            # ------------------------------------------------
            # Hochgeladene PDF speichern
            # ------------------------------------------------

            pdf_path = os.path.join(
                work_dir,
                uploaded_file.name
            )

            with open(pdf_path, "wb") as file:
                file.write(uploaded_file.getbuffer())


            # ------------------------------------------------
            # PDF öffnen
            # ------------------------------------------------

            doc = fitz.open(pdf_path)

            output_docs = {}
            skipped_pages = []

            # Regex nur für normale Textfelder vorbereiten
            pattern = None

            if regex_pattern:
                pattern = re.compile(
                    regex_pattern,
                    re.MULTILINE
                )


            # ------------------------------------------------
            # Jede Seite einzeln verarbeiten
            # ------------------------------------------------

            for page_number in range(len(doc)):

                page = doc[page_number]
                text = page.get_text()

                wert = None

                # --------------------------------------------
                # Standort anhand der Koordinaten auslesen
                # --------------------------------------------

                if option == "Standort":

                    wert = extract_value_by_position(
                        page,
                        "Standort"
                    )

                # --------------------------------------------
                # Andere Felder über Regex auslesen
                # --------------------------------------------

                else:

                    if pattern:
                        match = pattern.search(text)

                        if match:
                            wert = match.group(1).strip()


                # --------------------------------------------
                # Keine Übereinstimmung
                # --------------------------------------------

                if not wert:
                    skipped_pages.append(page_number + 1)
                    continue


                # --------------------------------------------
                # Dateinamen bereinigen
                # --------------------------------------------

                wert = clean_filename(wert)

                if not wert:
                    skipped_pages.append(page_number + 1)
                    continue


                # --------------------------------------------
                # Neues Zieldokument pro Wert anlegen
                # --------------------------------------------

                if wert not in output_docs:
                    output_docs[wert] = fitz.open()


                # Seite in das passende Dokument kopieren
                output_docs[wert].insert_pdf(
                    doc,
                    from_page=page_number,
                    to_page=page_number
                )


            # Ursprungsdokument schließen
            doc.close()


            # ------------------------------------------------
            # Prüfen, ob Treffer gefunden wurden
            # ------------------------------------------------

            if not output_docs:

                st.error(
                    f"Keine Übereinstimmungen für "
                    f"'{feld_name}' gefunden."
                )

                if skipped_pages:
                    st.write(
                        "Nicht verarbeitete Seiten:",
                        skipped_pages
                    )

                st.stop()


            # ------------------------------------------------
            # Einzel-PDFs speichern
            # ------------------------------------------------

            created_files = []

            for wert, out_doc in output_docs.items():

                filename = f"{file_prefix}_{wert}.pdf"
                output_path = os.path.join(
                    output_dir,
                    filename
                )

                out_doc.save(output_path)
                out_doc.close()

                created_files.append(filename)


            # ------------------------------------------------
            # ZIP-Datei im Speicher erzeugen
            # ------------------------------------------------

            zip_buffer = BytesIO()

            with zipfile.ZipFile(
                zip_buffer,
                "w",
                zipfile.ZIP_DEFLATED
            ) as zipf:

                for filename in created_files:

                    file_path = os.path.join(
                        output_dir,
                        filename
                    )

                    zipf.write(
                        file_path,
                        arcname=filename
                    )


            # ------------------------------------------------
            # Ergebnis anzeigen
            # ------------------------------------------------

            st.success(
                f"✅ Fertig! {len(created_files)} PDF-Dateien erstellt."
            )

            st.write("Erstellte Dateien:")

            for filename in created_files:
                st.write(f"- {filename}")


            if skipped_pages:
                st.warning(
                    "Folgende Seiten konnten keinem Wert "
                    "zugeordnet werden: "
                    + ", ".join(map(str, skipped_pages))
                )


            # ------------------------------------------------
            # Download anbieten
            # ------------------------------------------------

            st.download_button(
                label="⬇️ ZIP herunterladen",
                data=zip_buffer.getvalue(),
                file_name=f"{file_prefix}_Output.zip",
                mime="application/zip"
            )
