class Problem(ValueError):
    def __init__(self, code, status=400, detail=None):
        super().__init__(code)
        self.status = status
        self.body = {'error': code}
        if detail:
            self.body['detail'] = detail
