import re

from swe_agent.swe_agent.processor.history_processor import HistoryProcessor


class ClosedWindowHistoryProcessor(HistoryProcessor):
    pattern = re.compile(r'^(\d+)\:.*?(\n|$)', re.MULTILINE)
    file_pattern = re.compile(r'\[File:\s+(.*)\s+\(\d+\s+lines\ total\)\]')

    def __call__(self, history):
        new_history = list()
        # For each value in history, keep track of which windows have been shown.
        # We want to mark windows that should stay open (they're the last window for a particular file)
        # Then we'll replace all other windows with a simple summary of the window (i.e. number of lines)
        windows = set()
        for entry in reversed(history):
            data = entry.copy()
            if data['role'] != 'user':
                new_history.append(entry)
                continue
            if data.get('is_demo', False):
                new_history.append(entry)
                continue
            matches = list(self.pattern.finditer(entry['content']))
            if len(matches) >= 1:
                file_match = self.file_pattern.search(entry['content'])
                if file_match:
                    file = file_match.group(1)
                else:
                    continue
                if file in windows:
                    start = matches[0].start()
                    end = matches[-1].end()
                    data['content'] = (
                        entry['content'][:start] +\
                        f'Outdated window with {len(matches)} lines omitted...\n' +\
                        entry['content'][end:]
                    )
                windows.add(file)
            new_history.append(data)
        history = list(reversed(new_history))
        return history
