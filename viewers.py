import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))

import chess
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from engine import format_score, validate_pgn
from ui_widgets import ChessBoard, captured_pieces
from utils import fmt_date, fmt_duration, fmt_number, result_text
from workers import AnalysisWorker


class GameViewerDialog(QWidget):
    favorite_toggled = pyqtSignal(str)

    def __init__(self, game, analyzer, is_favorite=False, parent=None, depth=12, movetime=150):
        super().__init__(parent, Qt.WindowType.Window)
        self.game = game
        self.analyzer = analyzer
        self.depth = depth
        self.movetime = movetime
        self.positions = []
        self.moves = []
        self.ply = 0
        self.playing = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.worker = None
        self._closed = False
        self.pgn_error = ""
        self.game_analysis = None
        self.setWindowTitle(f"{game.get('white', '')} vs {game.get('black', '')} — Insight8x8")
        self.resize(1240, 820)
        self.setMinimumSize(900, 620)
        self._parse_pgn()
        self._build_ui(is_favorite)
        self._set_ply(0)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self._set_ply(self.ply - 1))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self._set_ply(self.ply + 1))
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.toggle_play)

    def _parse_pgn(self):
        start_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        positions = []
        moves = []
        try:
            _, parsed = validate_pgn(self.game.get("pgn"))
        except ValueError as error:
            self.pgn_error = str(error)
            self.positions = [start_fen]
            self.moves = moves
            return
        board = parsed.board()
        positions.append(board.fen())
        for move in parsed.mainline_moves():
            san = board.san(move)
            from_square = chess.square_name(move.from_square)
            to_square = chess.square_name(move.to_square)
            captured = board.piece_at(move.to_square)
            captured_symbol = captured.symbol().lower() if captured else ""
            if board.is_en_passant(move):
                captured_symbol = "p"
            board.push(move)
            moves.append(
                {
                    "san": san,
                    "from": from_square,
                    "to": to_square,
                    "uci": move.uci(),
                    "captured": captured_symbol,
                    "color": "w" if len(moves) % 2 == 0 else "b",
                }
            )
            positions.append(board.fen())
        self.positions = positions or [start_fen]
        self.moves = moves

    def _build_ui(self, is_favorite):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        head = QFrame()
        head.setObjectName("viewerHead")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel(f"{self.game.get('white', '')} vs {self.game.get('black', '')}")
        title.setObjectName("viewerTitle")
        subtitle = QLabel(
            f"{fmt_date(self.game.get('date'))} · {self.game.get('timeClass', '')} · "
            f"{result_text(self.game.get('result'))} · {self.game.get('timeControl', '')}"
        )
        subtitle.setObjectName("muted")
        head_text = QVBoxLayout()
        head_text.addWidget(title)
        head_text.addWidget(subtitle)
        head_layout.addLayout(head_text)
        head_layout.addStretch()
        self.favorite_button = QPushButton("★ Saved" if is_favorite else "☆ Save")
        self.favorite_button.setObjectName("smallButton")
        self.favorite_button.clicked.connect(self._toggle_favorite)
        self.link_button = QPushButton("Chess.com ↗")
        self.link_button.setObjectName("smallButton")
        self.link_button.clicked.connect(self._open_link)
        close_button = QPushButton("Close")
        close_button.setObjectName("smallButton")
        close_button.clicked.connect(self.close)
        head_layout.addWidget(self.favorite_button)
        head_layout.addWidget(self.link_button)
        head_layout.addWidget(close_button)
        root.addWidget(head)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        self.board = ChessBoard()
        self.board.setMaximumWidth(620)
        left_layout.addWidget(self.board, 1)
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        self.captured_label = QLabel()
        self.captured_label.setObjectName("muted")
        self.captured_label.setWordWrap(True)
        left_layout.addWidget(self.status_label)
        left_layout.addWidget(self.captured_label)
        controls = QHBoxLayout()
        for text, slot in (
            ("First", self._first),
            ("Previous", self._previous),
            ("Play", self.toggle_play),
            ("Next", self._next),
            ("Last", self._last),
        ):
            button = QPushButton(text)
            button.setObjectName("smallButton")
            button.clicked.connect(slot)
            if text == "Play":
                self.play_button = button
            controls.addWidget(button)
        left_layout.addLayout(controls)
        playback = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, max(0, len(self.moves)))
        self.slider.valueChanged.connect(self._set_ply)
        self.speed = QComboBox()
        self.speed.addItems(["0.5×", "1×", "1.5×", "2×"])
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(self._restart_timer)
        playback.addWidget(self.slider, 1)
        playback.addWidget(self.speed)
        left_layout.addLayout(playback)
        tools = QHBoxLayout()
        flip = QPushButton("Flip board")
        flip.setObjectName("smallButton")
        flip.clicked.connect(self._flip)
        download = QPushButton("Download PGN")
        download.setObjectName("smallButton")
        download.clicked.connect(self._download_pgn)
        copy = QPushButton("Copy PGN")
        copy.setObjectName("smallButton")
        copy.clicked.connect(self._copy_pgn)
        tools.addWidget(flip)
        tools.addWidget(download)
        tools.addWidget(copy)
        left_layout.addLayout(tools)
        splitter.addWidget(left)

        right = QScrollArea()
        right.setWidgetResizable(True)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(12)
        meta = QFrame()
        meta.setObjectName("panel")
        meta_grid = QGridLayout(meta)
        meta_grid.setContentsMargins(14, 12, 14, 12)
        entries = [
            ("Your rating", fmt_number(self.game.get("playerRating"))),
            ("Opponent", fmt_number(self.game.get("opponentRating"))),
            ("You played", self.game.get("color", "").title()),
            ("Result", result_text(self.game.get("result"))),
            ("Moves", fmt_number(self.game.get("moves"))),
            ("Duration", fmt_duration(self.game.get("durationSeconds"))),
        ]
        for index, (label, value) in enumerate(entries):
            row, col = divmod(index, 3)
            caption = QLabel(label.upper())
            caption.setObjectName("statTitle")
            value_label = QLabel(value)
            value_label.setObjectName("statValueSmall")
            meta_grid.addWidget(caption, row * 2, col)
            meta_grid.addWidget(value_label, row * 2 + 1, col)
        right_layout.addWidget(meta)

        moves_frame = QFrame()
        moves_frame.setObjectName("panel")
        moves_layout = QVBoxLayout(moves_frame)
        moves_layout.setContentsMargins(10, 10, 10, 10)
        moves_head = QLabel("MOVE HISTORY")
        moves_head.setObjectName("sectionLabel")
        moves_layout.addWidget(moves_head)
        self.move_list = QListWidget()
        self.move_list.setMaximumHeight(230)
        self.move_list.itemClicked.connect(self._move_clicked)
        self._fill_move_list()
        moves_layout.addWidget(self.move_list)
        right_layout.addWidget(moves_frame)

        analysis_frame = QFrame()
        analysis_frame.setObjectName("panel")
        analysis_layout = QVBoxLayout(analysis_frame)
        analysis_layout.setContentsMargins(14, 12, 14, 12)
        analysis_head = QLabel("GAME ANALYSIS")
        analysis_head.setObjectName("sectionLabel")
        analysis_layout.addWidget(analysis_head)
        opening = self.game.get("opening") or "Unknown opening"
        eco = self.game.get("eco") or "—"
        accuracy = self.game.get("accuracy")
        opponent_accuracy = self.game.get("opponentAccuracy")
        accuracy_text = f"{accuracy}%" if accuracy is not None else "Not provided by source"
        opponent_text = f"{opponent_accuracy}%" if opponent_accuracy is not None else "Not provided"
        self.detail_label = QLabel()
        self.detail_label.setWordWrap(True)
        self.detail_label.setText(
            f"Opening: {opening}\n"
            f"ECO: {eco}\n"
            f"Your accuracy: {accuracy_text}\n"
            f"Opponent accuracy: {opponent_text}"
        )
        self.detail_label.setObjectName("muted")
        analysis_layout.addWidget(self.detail_label)
        self.analysis_note = QLabel(
            "Stockfish checks every move locally: best move, evaluations, top candidates, variations and tactics."
        )
        self.analysis_note.setObjectName("muted")
        self.analysis_note.setWordWrap(True)
        analysis_layout.addWidget(self.analysis_note)
        self.engine_button = QPushButton("Analyze all moves")
        self.engine_button.setObjectName("smallButton")
        self.engine_button.setEnabled(bool(self.analyzer and self.analyzer.available and self.moves))
        self.engine_button.clicked.connect(self._analyze)
        analysis_layout.addWidget(self.engine_button)
        self.settings_button = QPushButton("Engine settings…")
        self.settings_button.setObjectName("smallButton")
        self.settings_button.setToolTip("Choose the Stockfish executable and analysis depth")
        self.settings_button.clicked.connect(self._open_engine_settings)
        analysis_layout.addWidget(self.settings_button)
        self.analysis_progress = QLabel()
        self.analysis_progress.setObjectName("muted")
        self.analysis_progress.setWordWrap(True)
        if self.pgn_error:
            self.analysis_progress.setText(f"PGN problem: {self.pgn_error}")
        elif not self.moves:
            self.analysis_progress.setText("This game has no replayable moves in the cached PGN.")
        elif not (self.analyzer and self.analyzer.available):
            path_error = getattr(self.analyzer, "path_error", "") if self.analyzer else ""
            message = path_error or "Stockfish is not configured."
            self.analysis_progress.setText(f"{message} Use Engine settings to locate it.")
        else:
            self.analysis_progress.setText(
                f"Stockfish ready · depth {self.depth} · {self.movetime} ms per position"
            )
        analysis_layout.addWidget(self.analysis_progress)
        self.engine_result_label = QLabel()
        self.engine_result_label.setObjectName("engineResult")
        self.engine_result_label.setWordWrap(True)
        analysis_layout.addWidget(self.engine_result_label)
        self.analysis_summary_label = QLabel()
        self.analysis_summary_label.setObjectName("muted")
        self.analysis_summary_label.setWordWrap(True)
        analysis_layout.addWidget(self.analysis_summary_label)
        right_layout.addWidget(analysis_frame)

        pgn_frame = QFrame()
        pgn_frame.setObjectName("panel")
        pgn_layout = QVBoxLayout(pgn_frame)
        pgn_layout.setContentsMargins(10, 10, 10, 10)
        pgn_head = QLabel("PGN")
        pgn_head.setObjectName("sectionLabel")
        pgn_layout.addWidget(pgn_head)
        self.pgn_box = QPlainTextEdit(self.game.get("pgn") or "")
        self.pgn_box.setReadOnly(True)
        self.pgn_box.setMaximumHeight(150)
        font = QFont("monospace")
        font.setPointSize(9)
        self.pgn_box.setFont(font)
        pgn_layout.addWidget(self.pgn_box)
        right_layout.addWidget(pgn_frame)
        right_layout.addStretch()
        right.setWidget(right_widget)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

    def _set_ply(self, ply):
        if not self.positions:
            return
        self.ply = max(0, min(int(ply), len(self.moves)))
        self.board.set_position(
            self.positions[self.ply],
            self.moves[self.ply - 1] if self.ply else None,
            self.board.orientation,
        )
        fen = self.positions[self.ply]
        turn = "White" if fen.split(" ")[1] == "w" else "Black"
        move_text = self.moves[self.ply - 1]["san"] if self.ply else "Starting position"
        self.status_label.setText(f"{self.ply}. {move_text}    {turn} to move")
        white_captured, black_captured = captured_pieces(self.moves, self.ply)
        self.captured_label.setText(
            f"White captured: {white_captured or '—'}     Black captured: {black_captured or '—'}"
        )
        self.slider.blockSignals(True)
        self.slider.setValue(self.ply)
        self.slider.blockSignals(False)
        any_selected = False
        for index in range(self.move_list.count()):
            item = self.move_list.item(index)
            selected = item.data(Qt.ItemDataRole.UserRole) == self.ply
            item.setSelected(selected)
            any_selected = any_selected or selected
        if not any_selected:
            self.move_list.clearSelection()
        entry = (self.game_analysis or {}).get("moves", {}).get(self.ply)
        self.engine_result_label.setText(self._format_analysis_entry(entry) if entry else "")

    def _fill_move_list(self):
        self.move_list.clear()
        markers = {"blunder": "??", "mistake": "?", "inaccuracy": "?!"}
        entries = (self.game_analysis or {}).get("moves") or {}
        for index, move in enumerate(self.moves):
            number = index // 2 + 1
            prefix = f"{number}." if index % 2 == 0 else f"{number}..."
            entry = entries.get(index + 1) or {}
            marker = markers.get(entry.get("classification"), "")
            self.move_list.addItem(f"{prefix} {move['san']}{marker}")
            self.move_list.item(self.move_list.count() - 1).setData(Qt.ItemDataRole.UserRole, index + 1)

    def _move_clicked(self, item):
        self._set_ply(int(item.data(Qt.ItemDataRole.UserRole)))

    def _first(self):
        self._set_ply(0)

    def _previous(self):
        self._set_ply(self.ply - 1)

    def _next(self):
        self._set_ply(self.ply + 1)

    def _last(self):
        self._set_ply(len(self.moves))

    def _advance(self):
        if self.ply >= len(self.moves):
            self.toggle_play()
            return
        self._set_ply(self.ply + 1)

    def toggle_play(self):
        if not self.moves:
            return
        if self.playing:
            self.playing = False
            self.timer.stop()
            self.play_button.setText("Play")
            return
        if self.ply >= len(self.moves):
            self._set_ply(0)
        self.playing = True
        self.play_button.setText("Pause")
        self._restart_timer()

    def _restart_timer(self):
        values = [0.5, 1.0, 1.5, 2.0]
        speed = values[self.speed.currentIndex()]
        self.timer.setInterval(max(150, int(1000 / speed)))
        if self.playing:
            self.timer.start()

    def _flip(self):
        self.board.orientation = "black" if self.board.orientation == "white" else "white"
        self._set_ply(self.ply)

    def _toggle_favorite(self):
        self.favorite_toggled.emit(self.game["id"])

    def set_favorite(self, value):
        self.favorite_button.setText("★ Saved" if value else "☆ Save")

    def _open_link(self):
        url = self.game.get("url")
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _download_pgn(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save PGN",
            f"{self.game.get('white', 'game')}-vs-{self.game.get('black', 'pgn')}.pgn",
            "PGN files (*.pgn);;All files (*)",
        )
        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as handle:
                    handle.write(self.game.get("pgn") or "")
            except OSError as error:
                QMessageBox.warning(self, "Save PGN", f"Could not save PGN:\n{error}")

    def _copy_pgn(self):
        QApplication.clipboard().setText(self.game.get("pgn") or "")

    def _open_engine_settings(self):
        parent = self.parent()
        if parent is None or not hasattr(parent, "_open_settings"):
            QMessageBox.information(self, "Insight8x8", "Open Engine settings from the main window first.")
            return
        parent._open_settings()
        self.analyzer = parent.analyzer
        options = parent._analysis_options()
        self.depth = options["depth"]
        self.movetime = options["movetime"]
        self.engine_button.setEnabled(bool(self.analyzer and self.analyzer.available and self.moves))
        if self.analyzer.available:
            self.analysis_progress.setText(
                f"Stockfish ready · depth {self.depth} · {self.movetime} ms per position"
            )
        else:
            self.analysis_progress.setText("Stockfish is not configured. Use Engine settings to locate it.")

    def _analyze(self):
        if not self.analyzer or not self.analyzer.available or not self.moves:
            return
        if self.worker is not None and self.worker.isRunning():
            return
        self.engine_button.setEnabled(False)
        self.engine_button.setText("Analyzing…")
        self.analysis_progress.setText("Starting Stockfish analysis…")
        worker = AnalysisWorker(
            self.analyzer, self.positions, self.moves, depth=self.depth, movetime=self.movetime
        )
        self.worker = worker

        def cleanup(current=worker):
            if self.worker is current:
                self.worker = None
            current.deleteLater()

        worker.progressed.connect(self._analysis_progress)
        worker.succeeded.connect(self._analysis_ready)
        worker.failed.connect(self._analysis_failed)
        worker.finished.connect(cleanup)
        worker.start()

    def _analysis_progress(self, done, total):
        if self._closed:
            return
        self.analysis_progress.setText(f"Analyzed {done} / {total} positions…")

    def _analysis_ready(self, result):
        if self._closed:
            return
        self.game_analysis = result
        self.engine_button.setEnabled(True)
        self.engine_button.setText("Analyze all moves")
        self.analysis_progress.setText(f"Analysis complete · {len(result.get('moves') or {})} moves")
        self.analysis_summary_label.setText(self._format_analysis_summary(result))
        self._fill_move_list()
        self._set_ply(self.ply)

    def _analysis_failed(self, message):
        if self._closed:
            return
        self.engine_button.setEnabled(True)
        self.engine_button.setText("Analyze all moves")
        self.analysis_progress.setText(f"Analysis failed: {message}")

    def _format_analysis_entry(self, entry):
        if not entry:
            return ""
        color = "White" if entry.get("color") == "w" else "Black"
        suffix = "." if color == "White" else "..."
        lines = [
            f"Move {entry['ply']}{suffix} {entry.get('move')} ({color})",
            f"Best move: {entry.get('bestMoveSan') or '—'}",
            f"Evaluation before ({color}): {format_score(entry.get('evalBefore'))}",
            f"Evaluation after ({color}): {format_score(entry.get('evalAfter'))}",
        ]
        loss = entry.get("centipawnLoss")
        classification = entry.get("classification")
        if loss is not None:
            lines.append(f"Centipawn loss: {fmt_number(loss)} — {classification}")
        elif classification:
            lines.append(f"Classification: {classification}")
        candidates = entry.get("candidates") or []
        if candidates:
            lines.append("Top 3 candidates:")
            for candidate in candidates[:3]:
                pv = " ".join(candidate.get("pv") or [])
                line = (
                    f"  {candidate.get('rank')}. {candidate.get('san')} "
                    f"{format_score(candidate.get('score'))}"
                )
                if pv:
                    line += f"  PV: {pv}"
                lines.append(line)
        opportunities = entry.get("tacticalOpportunities") or []
        if opportunities:
            lines.append("Tactical opportunities:")
            lines.extend(f"  • {text}" for text in opportunities)
        return "\n".join(lines)

    def _format_analysis_summary(self, result):
        summary = result.get("summary") or {}
        lines = [
            f"Analyzed {summary.get('classified', 0)} of {summary.get('moves', 0)} moves · "
            f"Blunders {summary.get('blunders', 0)} · Mistakes {summary.get('mistakes', 0)} · "
            f"Inaccuracies {summary.get('inaccuracies', 0)} · Best/good {summary.get('bestOrGood', 0)}"
        ]
        opportunities = result.get("opportunities") or []
        if opportunities:
            lines.append(f"Tactical opportunities ({len(opportunities)}):")
            for item in opportunities[:12]:
                suffix = "." if item.get("color") == "w" else "..."
                lines.append(f"  {item['ply']}{suffix} {item.get('move')}: {item.get('text')}")
            if len(opportunities) > 12:
                lines.append(f"  ... and {len(opportunities) - 12} more")
        else:
            lines.append("No tactical opportunities detected.")
        return "\n".join(lines)

    def closeEvent(self, event):
        self.timer.stop()
        self._closed = True
        event.accept()
