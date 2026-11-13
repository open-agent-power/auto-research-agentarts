"""Fixed document-level lexical pair from the frozen G5-L CPU study.

These pure functions have no file, model, network or project-state access.
Citation retrieval is not support/refute classification or scientific review.
"""
from collections import Counter, defaultdict
import math
import re

METHODS = ("tfidf_cosine", "bm25")
METRICS = ("recall@5", "recall@10", "recall@20", "mrr@10", "ndcg@10")


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def build_index(docs):
    postings, lengths = defaultdict(list), {}
    for doc_id in sorted(docs):
        row = docs[doc_id]
        terms = Counter(tokens(row["title"] + " " + row["text"]))
        lengths[doc_id] = sum(terms.values())
        for term, count in terms.items():
            postings[term].append((doc_id, count))
    n = len(docs)
    idfs = {term: math.log((n + 1) / (len(rows) + 1)) + 1 for term, rows in postings.items()}
    normsq = defaultdict(float)
    for term, rows in postings.items():
        for doc_id, count in rows:
            normsq[doc_id] += ((1 + math.log(count)) * idfs[term]) ** 2
    norms = {doc: math.sqrt(value) for doc, value in normsq.items()}
    return postings, lengths, idfs, norms, n, sum(lengths.values()) / n


def retrieve(query, index, method):
    postings, lengths, idfs, norms, n, avgdl = index
    counts = Counter(tokens(query))
    score = defaultdict(float)
    if method == "tfidf_cosine":
        qweights = {term: (1 + math.log(count)) * idfs[term] for term, count in counts.items() if term in idfs}
        qnorm = math.sqrt(sum(value * value for value in qweights.values()))
        for term, weight in qweights.items():
            for doc, tf in postings[term]:
                score[doc] += weight * ((1 + math.log(tf)) * idfs[term]) / (qnorm * norms[doc])
    elif method == "bm25":
        k1, b = 1.2, 0.75
        for term in counts:
            rows = postings.get(term, ())
            idf = math.log(1 + (n - len(rows) + .5) / (len(rows) + .5))
            for doc, tf in rows:
                score[doc] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lengths[doc] / avgdl))
    else:
        raise ValueError("Unknown fixed retrieval method")
    return sorted(score, key=lambda doc: (-score[doc], doc))[:20]


def metrics(ranking, relevant):
    relevant = set(relevant)
    result = {f"recall@{k}": len(set(ranking[:k]) & relevant) / len(relevant) if relevant else 0.
              for k in (5, 10, 20)}
    result["mrr@10"] = next((1 / (index + 1) for index, doc in enumerate(ranking[:10]) if doc in relevant), 0.)
    dcg = sum(1 / math.log2(index + 2) for index, doc in enumerate(ranking[:10]) if doc in relevant)
    ideal = sum(1 / math.log2(index + 2) for index in range(min(10, len(relevant))))
    result["ndcg@10"] = dcg / ideal if ideal else 0.
    return result
