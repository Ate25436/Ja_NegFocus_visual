from difflib import SequenceMatcher


def sentence_diff(original, rewritten):
    return [
        {"type": tag, "original": original[i:j], "rewritten": rewritten[k:l]}
        for tag, i, j, k, l in SequenceMatcher(
            None, original, rewritten, autojunk=False
        ).get_opcodes()
    ]
