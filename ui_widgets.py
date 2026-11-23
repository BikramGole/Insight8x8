from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QUrl
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

FILES = "abcdefgh"
PIECE_GLYPHS = {"p": "♟", "r": "♜", "n": "♞", "b": "♝", "q": "♛", "k": "♚"}


def rounded_pixmap(pixmap, size):
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    scaled = pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return result


class AvatarLabel(QLabel):
    def __init__(self, parent=None, size=64):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("avatar")
        self.set_text_avatar("?")
        self._pending_url = QUrl()
        self._manager = QNetworkAccessManager(self)
        self._manager.finished.connect(self._on_loaded)

    def set_text_avatar(self, value):
        text = str(value or "?").strip()
        self.setPixmap(QPixmap())
        self.setText(text[:1].upper() if text else "?")

    def set_url(self, url):
        self.set_text_avatar("?")
        self._pending_url = QUrl(str(url)) if url else QUrl("about:blank")
        if not url:
            return
        request = QNetworkRequest(self._pending_url)
        request.setRawHeader(b"User-Agent", b"Insight8x8Desktop/1.0")
        self._manager.get(request)

    def _on_loaded(self, reply):
        if self._pending_url.isValid() and reply.url().toString() != self._pending_url.toString():
            reply.deleteLater()
            return
        image = QImage.fromData(reply.readAll().data())
        reply.deleteLater()
        if image.isNull():
            return
        self.setPixmap(rounded_pixmap(QPixmap.fromImage(image), self._size))


class StatCard(QFrame):
    def __init__(self, title, value, hint="", color=None, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(5)
        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("statTitle")
        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("statValue")
        if color:
            self.value_label.setStyleSheet(f"color: {color};")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("statHint")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        if hint:
            layout.addWidget(self.hint_label)

    def set_value(self, value, hint=None):
        self.value_label.setText(str(value))
        if hint is not None:
            self.hint_label.setText(hint)


class DonutChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = []
        self.labels = []
        self.colors = []
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, labels, values, colors):
        self.labels = labels
        self.values = values
        self.colors = colors
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 40
        side = max(60, side)
        rect = QRect(
            (self.width() - side) // 2,
            (self.height() - side) // 2,
            side,
            side,
        )
        pen = QPen(QColor("#1a251f"), 18)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawEllipse(rect)
        total = sum(self.values)
        if total:
            start = -90 * 16
            for label, value, color in zip(self.labels, self.values, self.colors):
                if not value:
                    continue
                span = int((value / total) * 360 * 16)
                pen = QPen(QColor(color), 18)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(pen)
                painter.drawArc(rect, start, span)
                start += span
        painter.setPen(QColor("#edf5ef"))
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{total:,}")
        painter.setPen(QColor("#9bad9f"))
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        legend_y = rect.bottom() + 16
        x = 14
        for label, value, color in zip(self.labels, self.values, self.colors):
            painter.fillRect(QRect(x, legend_y, 9, 9), QColor(color))
            painter.setPen(QColor("#9bad9f"))
            painter.drawText(QRect(x + 14, legend_y - 3, 90, 16), Qt.AlignmentFlag.AlignLeft, f"{label} {value}")
            x += min(115, self.width() // max(1, len(self.labels)))


class LineChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels = []
        self.series = []
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, labels, series):
        self.labels = labels
        self.series = series
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, right, top, bottom = 52, 18, 22, 46
        chart = QRect(left, top, self.width() - left - right, self.height() - top - bottom)
        if chart.width() <= 10 or chart.height() <= 10:
            return
        painter.setPen(QColor("#223329"))
        painter.drawRect(chart)
        all_values = [value for series in self.series for value in series["values"] if value is not None]
        if not all_values:
            painter.setPen(QColor("#9bad9f"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No rating history yet")
            return
        min_value = min(all_values)
        max_value = max(all_values)
        if min_value == max_value:
            min_value -= 50
            max_value += 50
        else:
            padding = (max_value - min_value) * 0.12
            min_value -= padding
            max_value += padding
        for step in range(5):
            y = chart.bottom() - int((chart.height() * step) / 4)
            painter.setPen(QColor("#1d2a22"))
            painter.drawLine(left, y, chart.right(), y)
            painter.setPen(QColor("#6f8476"))
            value = min_value + ((max_value - min_value) * step) / 4
            painter.drawText(QRect(0, y - 9, left - 8, 18), Qt.AlignmentFlag.AlignRight, str(round(value)))
        count = max(1, len(self.labels) - 1)
        for index, label in enumerate(self.labels):
            if len(self.labels) > 8 and index % max(1, len(self.labels) // 7) and index != len(self.labels) - 1:
                continue
            x = chart.left() + int((chart.width() * index) / count)
            painter.setPen(QColor("#6f8476"))
            painter.drawText(QRect(x - 28, chart.bottom() + 8, 56, 18), Qt.AlignmentFlag.AlignCenter, label)
        for series in self.series:
            pen = QPen(QColor(series["color"]), 2.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            points = []
            for index, value in enumerate(series["values"]):
                if value is None:
                    continue
                x = chart.left() + int((chart.width() * index) / count)
                y = chart.bottom() - int(((value - min_value) / (max_value - min_value)) * chart.height())
                points.append(QPoint(x, y))
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)
            if points:
                painter.setBrush(QBrush(QColor(series["color"])))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(points[-1], 4, 4)
        x = left
        for series in self.series:
            painter.fillRect(QRect(x, 4, 9, 9), QColor(series["color"]))
            painter.setPen(QColor("#9bad9f"))
            painter.drawText(QRect(x + 13, 0, 90, 16), Qt.AlignmentFlag.AlignLeft, series["name"])
            x += 100


class BarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels = []
        self.values = []
        self.setMinimumHeight(230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, labels, values):
        self.labels = labels
        self.values = values
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, right, top, bottom = 22, 12, 16, 38
        chart = QRect(left, top, self.width() - left - right, self.height() - top - bottom)
        if not self.values or chart.width() <= 10:
            painter.setPen(QColor("#9bad9f"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No monthly activity yet")
            return
        maximum = max(self.values)
        slot = chart.width() / len(self.values)
        bar_width = max(6, int(slot * 0.62))
        for index, (label, value) in enumerate(zip(self.labels, self.values)):
            height = int((value / max(1, maximum)) * chart.height())
            x = chart.left() + int(index * slot + (slot - bar_width) / 2)
            y = chart.bottom() - height
            gradient = QColor("#5fd39a")
            painter.fillRect(QRect(x, y, bar_width, max(2, height)), gradient)
            painter.setPen(QColor("#9bad9f"))
            painter.drawText(QRect(x - 12, chart.bottom() + 8, bar_width + 24, 18), Qt.AlignmentFlag.AlignCenter, label)
            painter.drawText(QRect(x - 12, y - 18, bar_width + 24, 16), Qt.AlignmentFlag.AlignCenter, str(value))


def _fen_rows(fen):
    rows = []
    for row in str(fen).split(" ")[0].split("/"):
        expanded = ""
        for token in row:
            expanded += " " * int(token) if token.isdigit() else token
        rows.append(expanded)
    return rows


class ChessBoard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        self.last_move = None
        self.orientation = "white"
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        return QSize(520, 520)

    def set_position(self, fen, last_move=None, orientation=None):
        self.fen = fen
        self.last_move = last_move
        if orientation:
            self.orientation = orientation
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        if side < 8:
            return
        square = side / 8
        ox = (self.width() - side) / 2
        oy = (self.height() - side) / 2
        rows = _fen_rows(self.fen)
        font = QFont("DejaVu Sans")
        font.setPointSize(max(12, int(square * 0.62)))
        coord_font = QFont()
        coord_font.setPointSize(max(7, int(square * 0.16)))
        for display_row in range(8):
            source_row = display_row if self.orientation == "white" else 7 - display_row
            rank = 8 - source_row
            for display_col in range(8):
                source_col = display_col if self.orientation == "white" else 7 - display_col
                piece = rows[source_row][source_col] if source_col < len(rows[source_row]) else " "
                square_name = FILES[source_col] + str(rank)
                rect = QRect(
                    int(ox + display_col * square),
                    int(oy + display_row * square),
                    int(square + 0.6),
                    int(square + 0.6),
                )
                light = (rank + source_col) % 2 == 0
                painter.fillRect(rect, QColor("#cfd8c9") if light else QColor("#4d765d"))
                if self.last_move and square_name in (self.last_move.get("from"), self.last_move.get("to")):
                    pen = QPen(QColor("#d8b46a"), 3)
                    painter.setPen(pen)
                    painter.drawRect(rect.adjusted(2, 2, -2, -2))
                if piece != " ":
                    painter.setFont(font)
                    painter.setPen(QColor("#fffaf0") if piece.isupper() else QColor("#0c120e"))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, PIECE_GLYPHS[piece.lower()])
                painter.setFont(coord_font)
                painter.setPen(QColor("#1d2a22") if light else QColor("#edf5ef"))
                if display_col == 0:
                    painter.drawText(rect.adjusted(4, 0, 0, -3), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, str(rank))
                if display_row == 7:
                    painter.drawText(rect.adjusted(0, 2, -4, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, FILES[source_col])


def captured_pieces(moves, ply=None):
    upto = len(moves) if ply is None else max(0, min(int(ply), len(moves)))
    white_captured = []
    black_captured = []
    for move in moves[:upto]:
        glyph = PIECE_GLYPHS.get(move.get("captured"))
        if not glyph:
            continue
        if move.get("color") == "w":
            white_captured.append(glyph)
        else:
            black_captured.append(glyph)
    return "".join(white_captured), "".join(black_captured)
