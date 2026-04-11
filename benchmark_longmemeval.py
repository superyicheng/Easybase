#!/usr/bin/env python3
"""
Benchmark Easybase's BM25 against LongMemEval.

Runs Easybase's custom BM25 (with stopword removal, IDF floor, custom tokenizer)
and the standard BM25Okapi baseline side by side on LongMemEval retrieval tasks.

Usage:
    python3 benchmark_longmemeval.py --data_file ../longmemeval/data/longmemeval_s_cleaned.json
"""

import json
import math
import re
import sys
import os
import argparse
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

# Try to import rank_bm25 for baseline comparison
try:
    from rank_bm25 import BM25Okapi
    HAS_RANK_BM25 = True
except ImportError:
    HAS_RANK_BM25 = False
    print("Warning: rank_bm25 not installed. Will only run Easybase BM25.")

# ─── Easybase BM25 components (extracted from ctx.py) ───

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "need",
    "dare", "ought", "used", "it", "its", "this", "that", "these", "those",
    "he", "she", "we", "they", "me", "him", "her", "us", "them",
    "my", "his", "our", "their", "your",
    "not", "no", "nor", "so", "if", "then", "than", "too", "very",
    "just", "about", "above", "after", "again", "all", "also", "am",
    "any", "because", "before", "below", "between", "both", "each",
    "few", "further", "here", "how", "into", "more", "most", "much",
    "must", "now", "only", "other", "out", "over", "own", "same",
    "some", "such", "there", "through", "under", "until", "up", "when",
    "where", "which", "while", "who", "whom", "why", "what",
}

DEFAULT_K1 = 1.5
DEFAULT_B = 0.75
DEFAULT_IDF_FLOOR = 0.1


def easybase_tokenize(text):
    """Easybase's tokenizer: lowercase, regex-based, stopword removal."""
    text = text.lower()
    tokens = []

    for match in re.finditer(r"[a-z]{2,5}-\d{2,4}", text):
        tokens.append(match.group().replace("-", ""))

    for match in re.finditer(r"\d{4}-\d{2}-\d{2}", text):
        tokens.append(match.group().replace("-", ""))
        tokens.append(match.group()[:4])

    for match in re.finditer(r"[a-z][a-z0-9]+", text):
        word = match.group()
        if word not in STOPWORDS and len(word) > 1:
            tokens.append(word)

    return tokens


def easybase_bm25_search(query_tokens, corpus_tokens, k1=DEFAULT_K1, b=DEFAULT_B, idf_floor=DEFAULT_IDF_FLOOR):
    """
    Easybase's BM25 scoring. Returns indices sorted by descending score.

    corpus_tokens: list of token lists (one per document)
    query_tokens: token list for the query
    """
    N = len(corpus_tokens)
    if N == 0:
        return np.array([], dtype=int)

    doc_lengths = [len(doc) for doc in corpus_tokens]
    avgdl = sum(doc_lengths) / N

    # Build inverted index
    inverted = defaultdict(lambda: {"df": 0, "postings": {}})
    for doc_id, tokens in enumerate(corpus_tokens):
        tf = defaultdict(int)
        for token in tokens:
            tf[token] += 1
        for term, count in tf.items():
            if doc_id not in inverted[term]["postings"]:
                inverted[term]["df"] += 1
            inverted[term]["postings"][doc_id] = count

    # Score
    scores = defaultdict(float)
    for token in query_tokens:
        if token not in inverted:
            continue
        entry = inverted[token]
        df = entry["df"]
        postings = entry["postings"]

        idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
        idf = max(idf, idf_floor)

        for doc_id, tf in postings.items():
            dl = doc_lengths[doc_id]
            tf_sat = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
            scores[doc_id] += idf * tf_sat

    # Rank all documents (include zero-score ones at the end)
    scored_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ranked_ids = [doc_id for doc_id, _ in scored_docs]

    # Add unscored documents at the end
    all_ids = set(range(N))
    remaining = list(all_ids - set(ranked_ids))
    ranked_ids.extend(remaining)

    return np.array(ranked_ids)


# ─── LongMemEval evaluation functions (from eval_utils.py) ───

def dcg(relevances, k):
    relevances = np.asarray(relevances, dtype=float)[:k]
    if relevances.size:
        return relevances[0] + np.sum(relevances[1:] / np.log2(np.arange(2, relevances.size + 1)))
    return 0.


def ndcg(rankings, correct_docs, corpus_ids, k=10):
    relevances = [1 if doc_id in correct_docs else 0 for doc_id in corpus_ids]
    sorted_relevances = [relevances[idx] for idx in rankings[:k]]
    ideal_relevance = sorted(relevances, reverse=True)
    ideal_dcg = dcg(ideal_relevance, k)
    actual_dcg = dcg(sorted_relevances, k)
    if ideal_dcg == 0:
        return 0.
    return actual_dcg / ideal_dcg


def evaluate_retrieval(rankings, correct_docs, corpus_ids, k=10):
    recalled_docs = set(corpus_ids[idx] for idx in rankings[:k])
    recall_any = float(any(doc in recalled_docs for doc in correct_docs))
    recall_all = float(all(doc in recalled_docs for doc in correct_docs))
    ndcg_score = ndcg(rankings, correct_docs, corpus_ids, k)
    return recall_any, recall_all, ndcg_score


def evaluate_retrieval_turn2session(rankings, correct_docs, corpus_ids, k=10):
    def strip_turn_id(docid):
        return '_'.join(docid.split('_')[:-1])
    correct_docs = list(set([strip_turn_id(x) for x in correct_docs]))
    corpus_ids_stripped = [strip_turn_id(x) for x in corpus_ids]
    effective_k = k
    unique_docids = set(corpus_ids_stripped[idx] for idx in rankings[:effective_k])
    while effective_k <= len(corpus_ids_stripped) and len(unique_docids) < k:
        effective_k += 1
        unique_docids = set(corpus_ids_stripped[idx] for idx in rankings[:effective_k])
    return evaluate_retrieval(rankings, correct_docs, corpus_ids_stripped, k=effective_k)


# ─── Corpus construction (from run_retrieval.py) ───

def process_item_flat_index(data, granularity, sess_id, timestamp):
    corpus = []
    if granularity == 'session':
        text = ' '.join([interact['content'] for interact in data if interact['role'] == 'user'])
        corpus.append(text)
        ids = [sess_id]
        if 'answer' in sess_id and all([not turn.get('has_answer', False) for turn in [x for x in data if x['role'] == 'user']]):
            ids = [sess_id.replace('answer', 'noans')]
    elif granularity == 'turn':
        ids = []
        for i_turn, turn in enumerate(data):
            if turn['role'] == 'user':
                corpus.append(turn['content'])
                if 'answer' not in sess_id:
                    ids.append(sess_id + '_' + str(i_turn + 1))
                else:
                    if turn.get('has_answer', False):
                        ids.append(sess_id + '_' + str(i_turn + 1))
                    else:
                        ids.append((sess_id + '_' + str(i_turn + 1)).replace('answer', 'noans'))
    return corpus, ids, [timestamp for _ in corpus]


# ─── Main benchmark ───

def run_benchmark(data_file, granularity='session', max_questions=None):
    """Run Easybase BM25 and baseline BM25Okapi on LongMemEval."""

    print(f"\nLoading {data_file}...")
    with open(data_file) as f:
        data = json.load(f)

    if max_questions:
        data = data[:max_questions]

    n_abstention = len([x for x in data if '_abs' in x['question_id']])
    print(f"Loaded {len(data)} questions ({n_abstention} abstention)")
    print(f"Granularity: {granularity}")
    print()

    # Collect results for both retrievers
    easybase_metrics = []
    baseline_metrics = []

    start_time = time.time()

    for i, entry in enumerate(data):
        if (i + 1) % 50 == 0 or i == 0:
            elapsed = time.time() - start_time
            print(f"  Processing {i+1}/{len(data)} ({elapsed:.1f}s)")

        # Build corpus for this question
        corpus, corpus_ids, corpus_timestamps = [], [], []
        for cur_sess_id, sess_entry, ts in zip(
            entry['haystack_session_ids'],
            entry['haystack_sessions'],
            entry['haystack_dates']
        ):
            cur_items, cur_ids, cur_ts = process_item_flat_index(
                sess_entry, granularity, cur_sess_id, ts
            )
            corpus += cur_items
            corpus_ids += cur_ids
            corpus_timestamps += cur_ts

        correct_docs = list(set([doc_id for doc_id in corpus_ids if "answer" in doc_id]))
        corpus_ids = np.array(corpus_ids)
        query = entry['question']

        # ─── Easybase BM25 ───
        query_tokens = easybase_tokenize(query)
        corpus_tokens = [easybase_tokenize(doc) for doc in corpus]
        eb_rankings = easybase_bm25_search(query_tokens, corpus_tokens)

        eb_entry_metrics = {'session': {}, 'turn': {}}
        for k in [1, 3, 5, 10, 30, 50]:
            recall_any, recall_all, ndcg_any = evaluate_retrieval(
                eb_rankings, correct_docs, corpus_ids, k=k
            )
            eb_entry_metrics[granularity].update({
                f'recall_any@{k}': recall_any,
                f'recall_all@{k}': recall_all,
                f'ndcg_any@{k}': ndcg_any,
            })
            if granularity == 'turn':
                recall_any, recall_all, ndcg_any = evaluate_retrieval_turn2session(
                    eb_rankings, correct_docs, corpus_ids, k=k
                )
                eb_entry_metrics['session'].update({
                    f'recall_any@{k}': recall_any,
                    f'recall_all@{k}': recall_all,
                    f'ndcg_any@{k}': ndcg_any,
                })

        # ─── Baseline BM25Okapi ───
        bl_entry_metrics = {'session': {}, 'turn': {}}
        if HAS_RANK_BM25:
            tokenized_corpus = [doc.split(" ") for doc in corpus]
            bm25 = BM25Okapi(tokenized_corpus)
            scores = bm25.get_scores(query.split(" "))
            bl_rankings = np.argsort(scores)[::-1]

            for k in [1, 3, 5, 10, 30, 50]:
                recall_any, recall_all, ndcg_any = evaluate_retrieval(
                    bl_rankings, correct_docs, corpus_ids, k=k
                )
                bl_entry_metrics[granularity].update({
                    f'recall_any@{k}': recall_any,
                    f'recall_all@{k}': recall_all,
                    f'ndcg_any@{k}': ndcg_any,
                })
                if granularity == 'turn':
                    recall_any, recall_all, ndcg_any = evaluate_retrieval_turn2session(
                        bl_rankings, correct_docs, corpus_ids, k=k
                    )
                    bl_entry_metrics['session'].update({
                        f'recall_any@{k}': recall_any,
                        f'recall_all@{k}': recall_all,
                        f'ndcg_any@{k}': ndcg_any,
                    })

        # Skip abstention and no-target entries for metric aggregation
        skip = False
        if '_abs' in entry['question_id']:
            skip = True
        if not any(
            turn.get('has_answer', False)
            for sess in entry['haystack_sessions']
            for turn in sess
            if turn['role'] == 'user'
        ):
            skip = True

        if not skip:
            easybase_metrics.append(eb_entry_metrics)
            if HAS_RANK_BM25:
                baseline_metrics.append(bl_entry_metrics)

    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.1f}s ({len(data)} questions)")
    print(f"Evaluated on {len(easybase_metrics)} questions (excluded abstention + no-target)\n")

    # ─── Aggregate and print results ───
    def aggregate_metrics(metrics_list, level):
        agg = {}
        if not metrics_list or not metrics_list[0][level]:
            return agg
        for key in metrics_list[0][level]:
            values = [m[level][key] for m in metrics_list if key in m[level]]
            agg[key] = np.mean(values)
        return agg

    print("=" * 80)
    print(f"RESULTS — LongMemEval ({os.path.basename(data_file)}) — {granularity}-level retrieval")
    print("=" * 80)

    # Header
    key_metrics = ['recall_any@5', 'recall_all@5', 'ndcg_any@5',
                   'recall_any@10', 'recall_all@10', 'ndcg_any@10',
                   'recall_any@30', 'recall_all@30', 'ndcg_any@30',
                   'recall_any@50', 'recall_all@50', 'ndcg_any@50']

    for level in ['session', 'turn']:
        eb_agg = aggregate_metrics(easybase_metrics, level)
        if not eb_agg:
            continue

        print(f"\n--- {level.upper()}-level metrics ---")
        print(f"{'Metric':<20} {'Easybase BM25':>15}", end="")
        if HAS_RANK_BM25:
            bl_agg = aggregate_metrics(baseline_metrics, level)
            print(f" {'BM25Okapi':>15} {'Delta':>10}", end="")
        print()
        print("-" * 70)

        for metric in key_metrics:
            if metric not in eb_agg:
                continue
            eb_val = eb_agg[metric]
            print(f"{metric:<20} {eb_val:>15.4f}", end="")
            if HAS_RANK_BM25 and metric in bl_agg:
                bl_val = bl_agg[metric]
                delta = eb_val - bl_val
                sign = "+" if delta >= 0 else ""
                print(f" {bl_val:>15.4f} {sign}{delta:>9.4f}", end="")
            print()

    print()

    # Compact summary table
    print("=" * 80)
    print("COMPACT SUMMARY")
    print("=" * 80)

    for level in ['session', 'turn']:
        eb_agg = aggregate_metrics(easybase_metrics, level)
        if not eb_agg:
            continue
        print(f"\n{level.upper()}-level:")
        summary_metrics = ['recall_all@5', 'ndcg_any@5', 'recall_all@10', 'ndcg_any@10']

        row_eb = "  Easybase:  "
        row_bl = "  BM25Okapi: "
        for m in summary_metrics:
            if m in eb_agg:
                row_eb += f"{m}={eb_agg[m]:.4f}  "
        print(row_eb)

        if HAS_RANK_BM25:
            bl_agg = aggregate_metrics(baseline_metrics, level)
            for m in summary_metrics:
                if m in bl_agg:
                    row_bl += f"{m}={bl_agg[m]:.4f}  "
            print(row_bl)

    return easybase_metrics, baseline_metrics


def main():
    parser = argparse.ArgumentParser(description="Benchmark Easybase BM25 on LongMemEval")
    parser.add_argument('--data_file', type=str, required=True, help="Path to LongMemEval JSON file")
    parser.add_argument('--granularity', type=str, default='session', choices=['session', 'turn'])
    parser.add_argument('--max_questions', type=int, default=None, help="Limit number of questions (for quick test)")
    args = parser.parse_args()

    run_benchmark(args.data_file, args.granularity, args.max_questions)


if __name__ == '__main__':
    main()
