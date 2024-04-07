from swe_agent.swe_agent.processor.history_processor import HistoryProcessor


class LastNHistoryProcessor(HistoryProcessor):
    def last_n_history(history, n):
        if n <= 0:
            raise ValueError('n must be a positive integer')
        new_history = list()
        user_messages = len([entry for entry in history if (entry['role'] == 'user' and not entry.get('is_demo', False))])
        user_msg_idx = 0
        for entry in history:
            data = entry.copy()
            if data['role'] != 'user':
                new_history.append(entry)
                continue
            if data.get('is_demo', False):
                new_history.append(entry)
                continue
            else:
                user_msg_idx += 1
            if user_msg_idx == 1 or user_msg_idx in range(user_messages - n + 1, user_messages + 1):
                new_history.append(entry)
            else:
                data['content'] = f'Old output omitted ({len(entry["content"].splitlines())} lines)'
                new_history.append(data)
        return new_history


class LastNObservations(LastNHistoryProcessor):
    def __init__(self, n):
        self.n = n
    
    def __call__(self, history):
        return self.last_n_history(history, self.n)


class Last2Observations(LastNHistoryProcessor):
    def __call__(self, history):
        return self.last_n_history(history, 2)


class Last5Observations(LastNHistoryProcessor):
    def __call__(self, history):
        return self.last_n_history(history, 5)
