from PyQt6.QtCore import QThread, pyqtSignal


class FunctionWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self._function = function
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            self.succeeded.emit(self._function(*self._args, **self._kwargs))
        except Exception as error:
            self.failed.emit(str(error))


class AnalysisWorker(QThread):
    progressed = pyqtSignal(int, int)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        analyzer,
        fens,
        moves,
        depth=12,
        movetime=150,
        player_rating=None,
        opponent_rating=None,
        player_color=None,
    ):
        super().__init__()
        self.analyzer = analyzer
        self.fens = fens
        self.moves = moves
        self.depth = depth
        self.movetime = movetime
        self.player_rating = player_rating
        self.opponent_rating = opponent_rating
        self.player_color = player_color

    def run(self):
        try:
            def progress(done, total):
                self.progressed.emit(done, total)

            result = self.analyzer.analyze_game(
                self.fens,
                self.moves,
                depth=self.depth,
                movetime=self.movetime,
                progress=progress,
                player_rating=self.player_rating,
                opponent_rating=self.opponent_rating,
                player_color=self.player_color,
            )
            self.succeeded.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class ArchiveWorker(QThread):
    progressed = pyqtSignal(int, int)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, client, username, refresh=False):
        super().__init__()
        self.client = client
        self.username = username
        self.refresh = refresh

    def run(self):
        try:
            def progress(loaded, total):
                self.progressed.emit(loaded, total)

            result = self.client.load_games(
                self.username,
                force=self.refresh,
                progress=progress,
            )
            self.succeeded.emit(result)
        except Exception as error:
            self.failed.emit(str(error))
