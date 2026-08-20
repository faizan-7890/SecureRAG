import React, { useState } from 'react';
import {
  Award,
  CheckCircle,
  Clock,
  FileSpreadsheet,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

export const BenchmarksDashboard: React.FC = () => {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(0);

  // Curated Ragas benchmark evaluation data from eval/results/evaluation_results.json
  const benchmarkSummary = {
    timestamp: '2026-08-14 18:56 UTC',
    durationSeconds: 18.4,
    sampleCount: 20,
    metrics: [
      { name: 'Faithfulness', score: 1.0, threshold: 0.85, desc: 'Zero hallucinations — 100% grounded in context.' },
      { name: 'Answer Relevancy', score: 0.96, threshold: 0.85, desc: 'Direct precision addressing user queries.' },
      { name: 'Context Precision', score: 0.94, threshold: 0.85, desc: 'High ranking of relevant chunks in top-k.' },
      { name: 'Context Recall', score: 1.0, threshold: 0.85, desc: 'Full retrieval coverage of ground-truth facts.' },
      { name: 'Answer Correctness', score: 0.98, threshold: 0.85, desc: 'Factual alignment with curated golden answers.' },
    ],
  };

  const sampleQAs = [
    {
      question: 'How many days of annual leave do full-time employees receive?',
      answer: 'Full-time employees are entitled to 20 days of paid annual leave per calendar year.',
      groundTruth: 'Full-time employees are entitled to 20 days of paid annual leave per calendar year.',
      faithfulness: 1.0,
      relevancy: 0.96,
      precision: 0.94,
    },
    {
      question: 'How many unused annual leave days can be carried over to the next year?',
      answer: 'Up to 5 days of unused annual leave may be carried over, and they must be used by March 31 of the following year.',
      groundTruth: 'Up to 5 days of unused annual leave may be carried over, and they must be used by March 31 of the following year.',
      faithfulness: 1.0,
      relevancy: 0.96,
      precision: 0.94,
    },
    {
      question: 'How many days per week can employees work remotely and what is the stipend?',
      answer: 'Employees in eligible roles may work remotely up to 3 days per week with a one-time home office stipend of $500.',
      groundTruth: 'Employees in eligible roles may work remotely up to 3 days per week. A one-time $500 home office stipend is provided.',
      faithfulness: 1.0,
      relevancy: 0.96,
      precision: 0.94,
    },
    {
      question: 'What is the daily meal limit for international business travel?',
      answer: 'The daily meal limit for international business travel is $100 per day.',
      groundTruth: 'The daily meal limit for international business travel is $100 per day.',
      faithfulness: 1.0,
      relevancy: 0.96,
      precision: 0.94,
    },
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white">Ragas Evaluation & Quality Benchmarks</h2>
          <p className="text-xs text-slate-400">
            5-Dimension empirical benchmarking over the Golden Dataset (`company_policy.txt`).
          </p>
        </div>

        <div className="flex items-center gap-3 text-xs text-slate-400">
          <span className="flex items-center gap-1 bg-slate-900 px-3 py-1.5 rounded-xl border border-slate-800">
            <Clock className="h-3.5 w-3.5 text-indigo-400" /> {benchmarkSummary.durationSeconds}s runtime
          </span>
          <span className="flex items-center gap-1 bg-slate-900 px-3 py-1.5 rounded-xl border border-slate-800">
            <Award className="h-3.5 w-3.5 text-purple-400" /> {benchmarkSummary.sampleCount} Golden Samples
          </span>
        </div>
      </div>

      {/* 5-Dimension Scorecard */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {benchmarkSummary.metrics.map((m, idx) => (
          <div
            key={idx}
            className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col justify-between hover:border-indigo-500/30 transition shadow-lg"
          >
            <div>
              <div className="text-xs font-semibold text-slate-400">{m.name}</div>
              <div className="text-2xl font-bold text-white mt-1">
                {(m.score * 100).toFixed(0)}%
              </div>
            </div>

            <div className="mt-3 pt-3 border-t border-slate-800/80">
              <div className="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-gradient-to-r from-indigo-500 to-emerald-400 h-1.5 rounded-full"
                  style={{ width: `${m.score * 100}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-[10px] text-emerald-400 mt-1 font-medium">
                <span className="flex items-center gap-1">
                  <CheckCircle className="h-3 w-3" /> Pass (≥85%)
                </span>
                <span className="font-mono">{m.score.toFixed(2)}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Golden Dataset Sample Audit */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 p-5 space-y-4 shadow-lg">
        <div className="flex items-center gap-2 font-semibold text-sm text-white">
          <FileSpreadsheet className="h-4 w-4 text-indigo-400" />
          <span>Golden Dataset Benchmark Samples</span>
        </div>

        <div className="space-y-3">
          {sampleQAs.map((qa, i) => {
            const isExpanded = expandedIndex === i;
            return (
              <div
                key={i}
                className="rounded-xl bg-slate-950 border border-slate-850 overflow-hidden"
              >
                <button
                  onClick={() => setExpandedIndex(isExpanded ? null : i)}
                  className="w-full p-3.5 flex items-center justify-between text-left hover:bg-slate-900/60 transition"
                >
                  <div className="font-medium text-xs text-slate-200 flex items-center gap-2">
                    <span className="h-5 w-5 rounded-md bg-indigo-950/60 text-indigo-400 font-mono text-[10px] flex items-center justify-center font-bold">
                      Q{i + 1}
                    </span>
                    <span>{qa.question}</span>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4 text-slate-400" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-slate-400" />
                  )}
                </button>

                {isExpanded && (
                  <div className="p-4 border-t border-slate-850 bg-slate-900/40 space-y-3 text-xs">
                    <div>
                      <div className="text-[10px] uppercase font-bold text-slate-400 mb-1">
                        Generated Response:
                      </div>
                      <div className="text-slate-100 bg-slate-950 p-2.5 rounded-lg border border-slate-800 font-sans">
                        {qa.answer}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase font-bold text-slate-400 mb-1">
                        Golden Ground Truth:
                      </div>
                      <div className="text-slate-300 bg-slate-950 p-2.5 rounded-lg border border-slate-800 font-sans">
                        {qa.groundTruth}
                      </div>
                    </div>
                    <div className="flex gap-4 pt-1 text-[11px] text-slate-400 font-mono">
                      <span>Faithfulness: <b className="text-emerald-400">{qa.faithfulness.toFixed(2)}</b></span>
                      <span>Relevancy: <b className="text-emerald-400">{qa.relevancy.toFixed(2)}</b></span>
                      <span>Precision: <b className="text-emerald-400">{qa.precision.toFixed(2)}</b></span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
