"""A pass/warn/fail ledger. ok lines print as they happen; warnings, then failures,
print together at the end, so the problems are the last thing on the screen."""


class Report:
    def __init__(self, log=print):
        self.log = log
        self.oks, self.warns, self.fails = [], [], []

    def ok(self, test, msg):
        line = "[ ok ] %s: %s" % (test, msg)
        self.oks.append(line)
        if self.log:
            self.log(line)

    def warn(self, test, msg):
        self.warns.append("[warn] %s: %s" % (test, msg))

    def fail(self, test, msg):
        self.fails.append("[FAIL] %s: %s" % (test, msg))

    def check(self, test, good, msg):
        (self.ok if good else self.fail)(test, msg)

    def finish(self):
        """Print the tail and return an exit code: 1 if anything failed."""
        if self.log:
            self.log("")
            for w in self.warns:
                self.log(w)
            for f in self.fails:
                self.log(f)
            self.log("\n%d failures, %d warnings" % (len(self.fails), len(self.warns)))
        return 1 if self.fails else 0
