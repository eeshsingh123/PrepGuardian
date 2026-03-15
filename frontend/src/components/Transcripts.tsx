import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { MessageSquare, Clock, User, Bot, Download, FileText, Activity, AlertTriangle, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import {
  Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine, Area, ComposedChart,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  BarChart, Bar, Cell
} from 'recharts';
import { useAuth } from '../lib/auth';
import { fetchConversations, fetchConversation, generateInsights } from '../lib/api';
import type { ConversationSummary, ConversationFull, UserData } from '../lib/api';

interface TranscriptsProps {
  isDarkMode: boolean;
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

// Ensure unique IDs for components
let uniqueIdCounter = 0;
const getUniqueId = () => `id-${uniqueIdCounter++}`;

export function Transcripts({ isDarkMode }: TranscriptsProps) {
  const { user } = useAuth();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const dark = isDarkMode;

  const conversationsQuery = useQuery({
    queryKey: ['conversations', user?.user_id],
    queryFn: () => fetchConversations(user!.user_id),
    enabled: !!user,
  });

  const transcriptQuery = useQuery({
    queryKey: ['transcript', selectedSessionId],
    queryFn: () => fetchConversation(selectedSessionId!),
    enabled: !!selectedSessionId,
  });

  return (
    <div className="flex h-[calc(100vh-73px)] w-full">
      {/* Left Panel: Conversation List */}
      <div className={`w-80 flex-shrink-0 border-r flex flex-col ${dark ? 'border-gray-800 bg-[#0a0a0a]' : 'border-gray-200 bg-gray-50'}`}>
        <div className={`px-4 py-4 border-b ${dark ? 'border-gray-800' : 'border-gray-200'}`}>
          <h2 className={`text-xs font-bold uppercase tracking-widest ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
            Session History
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto">
          {conversationsQuery.isLoading && (
            <div className={`p-4 text-sm ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
              Loading sessions…
            </div>
          )}

          {conversationsQuery.isError && (
            <div className="p-4 text-sm text-red-500">
              Failed to load sessions.
            </div>
          )}

          {conversationsQuery.data?.length === 0 && (
            <div className={`p-6 text-center text-sm ${dark ? 'text-gray-600' : 'text-gray-400'}`}>
              <MessageSquare className="w-8 h-8 mx-auto mb-3 opacity-20" />
              <p>No insight sessions found.</p>
              <p className="mt-1 text-xs opacity-70">Start a session to record data.</p>
            </div>
          )}

          {conversationsQuery.data?.map((conv: ConversationSummary) => (
            <button
              key={conv.session_id}
              onClick={() => setSelectedSessionId(conv.session_id)}
              className={`w-full text-left px-5 py-4 border-b transition-all duration-200 ${
                selectedSessionId === conv.session_id
                  ? (dark ? 'bg-[#141414] border-l-4 border-l-sky-600 border-b-gray-800' : 'bg-white border-l-4 border-l-sky-600 border-b-gray-200 shadow-sm')
                  : (dark ? 'border-l-4 border-l-transparent border-gray-800/50 hover:bg-[#1a1a1a]' : 'border-l-4 border-l-transparent border-gray-100 hover:bg-gray-100/50')
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className={`text-xs font-medium ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
                  {formatDate(conv.started_at)}
                </span>
                <span className={`text-xs flex items-center gap-1.5 font-mono ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
                  <Clock className="w-3.5 h-3.5" />
                  {formatDuration(conv.duration_seconds)}
                </span>
              </div>
              <p className={`text-sm leading-relaxed line-clamp-2 ${dark ? 'text-gray-300' : 'text-gray-700'}`}>
                {conv.preview || 'No conversation recorded.'}
              </p>
              <div className={`flex items-center gap-3 mt-3 text-xs font-medium ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
                <span className="flex items-center gap-1.5"><MessageSquare className="w-3.5 h-3.5" /> {conv.turn_count} turns</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right Panel: Content Viewer */}
      <div className={`flex-1 flex flex-col overflow-hidden ${dark ? 'bg-[#0f0f0f]' : 'bg-white'}`}>
        {!selectedSessionId ? (
          <div className="flex-1 flex items-center justify-center">
            <div className={`text-center ${dark ? 'text-gray-600' : 'text-gray-400'}`}>
              <Activity className="w-12 h-12 mx-auto mb-4 opacity-30" />
              <h3 className="text-lg font-medium mb-1">Select a Session</h3>
              <p className="text-sm">View transcripts and AI-generated insights.</p>
            </div>
          </div>
        ) : transcriptQuery.isLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-4">
            <div className="w-8 h-8 rounded-full border-2 border-sky-500 border-t-transparent animate-spin"></div>
            <p className={`text-sm font-medium ${dark ? 'text-gray-400' : 'text-gray-500'}`}>Loading session data...</p>
          </div>
        ) : transcriptQuery.isError ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center text-red-500">
              <AlertTriangle className="w-12 h-12 mx-auto mb-4 opacity-80" />
              <h3 className="text-lg font-medium mb-1">Error Loading Session</h3>
              <p className="text-sm opacity-80">Could not retrieve the selected transcript.</p>
            </div>
          </div>
        ) : transcriptQuery.data ? (
          <DashboardView conversation={transcriptQuery.data} isDarkMode={dark} user={user} selectedSessionId={selectedSessionId} />
        ) : null}
      </div>
    </div>
  );
}

function DashboardView({
  conversation,
  isDarkMode,
  user,
  selectedSessionId,
}: {
  conversation: ConversationFull;
  isDarkMode: boolean;
  user: UserData | null | undefined;
  selectedSessionId: string | null;
}) {
  const [activeTab, setActiveTab] = useState<'transcript' | 'insights' | 'report'>('insights');
  const dark = isDarkMode;
  const queryClient = useQueryClient();
  const generateInsightsMutation = useMutation({
    mutationFn: () => generateInsights(user!.user_id, conversation.session_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcript', selectedSessionId] });
      queryClient.invalidateQueries({ queryKey: ['conversations', user?.user_id] });
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Insight generation failed. Please try again.';
      toast.error(message);
    },
  });

  const downloadTranscript = () => {
    let content = `Transcript: ${formatDate(conversation.started_at)}\n\n`;
    conversation.turns.forEach(t => {
      content += `[${formatTime(t.timestamp)}] ${t.role.toUpperCase()}:\n${t.text}\n\n`;
    });
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcript-${conversation.session_id}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadReport = () => {
    const text = conversation.report_text || "No report available.";
    const blob = new Blob([text], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report-${conversation.session_id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Dashboard Header & Tabs */}
      <div className={`px-8 pt-6 pb-0 border-b ${dark ? 'border-gray-800' : 'border-gray-200'}`}>
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className={`text-2xl font-semibold tracking-tight ${dark ? 'text-gray-100' : 'text-gray-900'}`}>
              Session Debrief
            </h1>
            <p className={`text-sm mt-1.5 flex items-center gap-3 ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
              <span className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> {formatDuration(conversation.duration_seconds)}</span>
              <span>•</span>
              <span className="flex items-center gap-1.5"><MessageSquare className="w-3.5 h-3.5" /> {conversation.turn_count} turns</span>
              <span>•</span>
              <span>{formatDate(conversation.started_at)}</span>
            </p>
          </div>
          
          <div className="flex flex-wrap gap-3 items-center">
            {user && (
              <button
                id={`generate-insights-${conversation.session_id}`}
                onClick={() => generateInsightsMutation.mutate()}
                disabled={generateInsightsMutation.isPending}
                className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                  dark
                    ? 'bg-sky-600 hover:bg-sky-500 text-white disabled:opacity-50 disabled:cursor-not-allowed'
                    : 'bg-sky-600 hover:bg-sky-700 text-white disabled:opacity-50 disabled:cursor-not-allowed'
                }`}
              >
                {generateInsightsMutation.isPending ? (
                  <>
                    <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    Generating…
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    Generate Insights
                  </>
                )}
              </button>
            )}
            <button
              id={`dl-txt-${conversation.session_id}`}
              onClick={downloadTranscript}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                dark ? 'bg-gray-800 hover:bg-gray-700 text-gray-200' : 'bg-white border border-gray-200 hover:bg-gray-50 text-gray-700'
              }`}
            >
              <Download className="w-4 h-4" />
              Transcript
            </button>
            {conversation.report_text && (
              <button
                id={`dl-md-${conversation.session_id}`}
                onClick={downloadReport}
                className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                  dark ? 'bg-sky-600/20 text-sky-400 hover:bg-sky-600/30' : 'bg-sky-50 text-sky-700 hover:bg-sky-100'
                }`}
              >
                <FileText className="w-4 h-4" />
                Report MD
              </button>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-8">
          {[
            { id: 'insights', label: 'Analysis Insights', icon: Activity },
            { id: 'report', label: 'Executive Report', icon: FileText },
            { id: 'transcript', label: 'Raw Transcript', icon: MessageSquare },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 pb-4 px-1 border-b-2 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? (dark ? 'border-sky-500 text-sky-400' : 'border-sky-600 text-sky-700')
                  : (dark ? 'border-transparent text-gray-500 hover:text-gray-300' : 'border-transparent text-gray-500 hover:text-gray-800')
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto relative bg-transparent">
        {activeTab === 'transcript' && <TranscriptTab conversation={conversation} isDarkMode={dark} />}
        {activeTab === 'insights' && <InsightsTab conversation={conversation} isDarkMode={dark} />}
        {activeTab === 'report' && <ReportTab conversation={conversation} isDarkMode={dark} />}
      </div>
    </div>
  );
}

function TranscriptTab({ conversation, isDarkMode }: { conversation: ConversationFull; isDarkMode: boolean }) {
  const dark = isDarkMode;
  return (
    <div className="max-w-4xl mx-auto px-8 py-8 space-y-6">
      {conversation.turns.map((turn, index) => (
        <div key={`turn-${index}`} className={`flex gap-4 ${turn.role === 'user' ? 'justify-end' : 'justify-start'}`}>
          {turn.role === 'agent' && (
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-1 shadow-sm ${dark ? 'bg-gradient-to-br from-sky-500/20 to-blue-500/10 text-sky-400 border border-sky-500/20' : 'bg-gradient-to-br from-sky-100 to-blue-50 text-sky-700 border border-sky-200'}`}>
              <Bot className="w-5 h-5" />
            </div>
          )}
          
          <div className={`max-w-[75%] px-5 py-4 rounded-2xl text-[15px] leading-relaxed shadow-sm ${
            turn.role === 'user'
              ? (dark
                  ? 'bg-blue-600/20 text-blue-50 border border-blue-500/30 rounded-tr-sm'
                  : 'bg-blue-50 text-blue-900 border border-blue-200 rounded-tr-sm')
              : (dark
                  ? 'bg-[#1a1a1a] text-gray-200 border border-gray-800/80 rounded-tl-sm'
                  : 'bg-white text-gray-800 border border-gray-200 rounded-tl-sm')
          }`}>
            <p className="whitespace-pre-wrap">{turn.text}</p>
            <span className={`block text-[11px] font-medium mt-2 tracking-wide uppercase ${
              turn.role === 'user'
                ? (dark ? 'text-blue-400/60' : 'text-blue-500/70')
                : (dark ? 'text-gray-500' : 'text-gray-400')
            }`}>
              {formatTime(turn.timestamp)}
            </span>
          </div>

          {turn.role === 'user' && (
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-1 shadow-sm ${dark ? 'bg-gradient-to-br from-blue-500/20 to-cyan-500/10 text-blue-400 border border-blue-500/20' : 'bg-gradient-to-br from-blue-100 to-cyan-50 text-blue-700 border border-blue-200'}`}>
              <User className="w-5 h-5" />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ReportTab({ conversation, isDarkMode }: { conversation: ConversationFull; isDarkMode: boolean }) {
  const dark = isDarkMode;
  
  if (!conversation.report_text) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className={`text-center ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
          <FileText className="w-12 h-12 mx-auto mb-4 opacity-20" />
          <p>No report generated yet.</p>
          <p className="text-sm mt-2 opacity-70">Reports take a moment to generate after a session ends.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`max-w-4xl mx-auto px-8 py-10 prose prose-lg ${dark ? 'prose-invert prose-p:text-gray-300 prose-headings:text-gray-100' : 'prose-p:text-gray-700'} pb-24`}>
      <ReactMarkdown>{conversation.report_text}</ReactMarkdown>
    </div>
  );
}

function InsightsTab({ conversation, isDarkMode }: { conversation: ConversationFull; isDarkMode: boolean }) {
  const dark = isDarkMode;
  
  if (!conversation.confidence_data && !conversation.radar_data && !conversation.market_gap_data) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className={`text-center ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
          <Activity className="w-12 h-12 mx-auto mb-4 opacity-20" />
          <p>Insights have not been generated for this session.</p>
          <p className="text-sm mt-2 opacity-70">If the session just ended, try reloading in a few moments.</p>
        </div>
      </div>
    );
  }

  const { confidence_data, radar_data, market_gap_data } = conversation;
  
  // Custom theme colors for charts
  const axisColor = dark ? "#525252" : "#d4d4d4";
  const textColor = dark ? "#a3a3a3" : "#737373";
  const gridColor = dark ? "#262626" : "#f5f5f5";
  const tooltipBg = dark ? "#171717" : "#ffffff";
  const tooltipBorder = dark ? "#262626" : "#e5e5e5";
  const tooltipText = dark ? "#e5e5e5" : "#171717";

  return (
    <div className="max-w-6xl mx-auto px-8 py-10 space-y-12 pb-24">
      
      {/* 1. Market Readiness Hero (If available) */}
      {market_gap_data && (
        <div className={`rounded-3xl p-8 border shadow-sm ${dark ? 'bg-[#141414] border-gray-800' : 'bg-white border-gray-100'}`}>
          <div className="flex flex-col md:flex-row items-center justify-between gap-8">
            <div className="flex-1">
              <p className={`text-sm font-bold tracking-widest uppercase mb-3 ${dark ? 'text-sky-400' : 'text-sky-600'}`}>
                Readiness Evaluation
              </p>
              <h2 className={`text-4xl sm:text-5xl font-extrabold tracking-tight mb-4 ${dark ? 'text-white' : 'text-gray-900'}`}>
                {market_gap_data.readiness_percentage}% Ready
              </h2>
              <div className="flex flex-wrap items-center gap-3 mb-6">
                <span className={`px-3 py-1 text-xs font-semibold rounded-full uppercase tracking-wider ${
                  market_gap_data.readiness_percentage >= 85 ? (dark ? 'bg-emerald-500/20 text-emerald-400' : 'bg-emerald-100 text-emerald-700') :
                  market_gap_data.readiness_percentage >= 70 ? (dark ? 'bg-blue-500/20 text-blue-400' : 'bg-blue-100 text-blue-700') :
                  market_gap_data.readiness_percentage >= 55 ? (dark ? 'bg-amber-500/20 text-amber-400' : 'bg-amber-100 text-amber-700') :
                  (dark ? 'bg-red-500/20 text-red-400' : 'bg-red-100 text-red-700')
                }`}>
                  {market_gap_data.readiness_label}
                </span>
                <span className={`text-sm font-medium ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Target: {market_gap_data.target_level} @ {market_gap_data.target_company}
                </span>
              </div>
              <p className={`text-base md:text-lg leading-relaxed ${dark ? 'text-gray-300' : 'text-gray-600'}`}>
                {market_gap_data.summary}
              </p>
            </div>
            
            {/* Market Gap Bar Chart */}
            <div className="w-full md:w-1/2 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={market_gap_data.dimensions} layout="vertical" margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={gridColor} />
                  <XAxis type="number" domain={[0, 10]} hide />
                  <YAxis dataKey="name" type="category" width={140} tick={{ fill: textColor, fontSize: 11, fontWeight: 500 }} axisLine={false} tickLine={false} />
                  <RechartsTooltip 
                    cursor={{ fill: dark ? '#262626' : '#f5f5f5' }}
                    contentStyle={{ backgroundColor: tooltipBg, borderColor: tooltipBorder, borderRadius: '12px', color: tooltipText, boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                  />
                  <Bar dataKey="candidate_score" name="Your Score" radius={[0, 4, 4, 0]} barSize={16}>
                    {market_gap_data.dimensions.map((entry, index) => {
                      const color = entry.gap <= 0 ? (dark ? '#34d399' : '#059669') : 
                                    entry.gap <= 2 ? (dark ? '#fbbf24' : '#d97706') : 
                                    (dark ? '#f87171' : '#dc2626');
                      return <Cell key={`cell-${index}`} fill={color} />;
                    })}
                  </Bar>
                  {/* We can't easily draw per-bar reference lines in standard Recharts BarChart without custom shapes, but a custom shape is complex. We will use a composed chart with a scatter for the target or just rely on the tooltip. Actually, Recharts allows ReferenceLine on continuous axes. Since Y is category, we can't draw vertical lines per category easily. Let's just use the bar color to convey the gap. */}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Grid for Radar & Confidence */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
        
        {/* 2. Concept Radar */}
        {radar_data && (
          <div className={`rounded-3xl p-8 border shadow-sm flex flex-col ${dark ? 'bg-[#141414] border-gray-800' : 'bg-white border-gray-100'}`}>
            <h3 className={`text-lg font-semibold mb-6 ${dark ? 'text-gray-100' : 'text-gray-900'}`}>Concept Coverage</h3>
            
            <div className="flex-1 w-full flex items-center justify-center min-h-[350px] -mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart 
                  cx="50%" cy="50%" outerRadius="70%" 
                  data={Object.entries(radar_data.pillars).map(([key, val]) => ({ subject: key, score: val, fullMark: 10 }))}
                >
                  <PolarGrid stroke={gridColor} />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: textColor, fontSize: 11, fontWeight: 500 }} />
                  <PolarRadiusAxis angle={30} domain={[0, 10]} tick={{ fill: axisColor, fontSize: 10 }} />
                  <Radar name="Candidate Score" dataKey="score" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.3} />
                  <RechartsTooltip contentStyle={{ backgroundColor: tooltipBg, borderColor: tooltipBorder, borderRadius: '8px', color: tooltipText }} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div className="grid grid-cols-2 gap-4 mt-6">
              <div className={`p-4 rounded-xl border ${dark ? 'bg-green-500/5 border-green-500/10' : 'bg-green-50 border-green-100'}`}>
                <p className={`text-xs uppercase font-bold tracking-widest mb-1 ${dark ? 'text-green-500' : 'text-green-700'}`}>Strongest</p>
                <p className={`font-semibold ${dark ? 'text-gray-200' : 'text-gray-800'}`}>{radar_data.strongest}</p>
              </div>
              <div className={`p-4 rounded-xl border ${dark ? 'bg-red-500/5 border-red-500/10' : 'bg-red-50 border-red-100'}`}>
                <p className={`text-xs uppercase font-bold tracking-widest mb-1 ${dark ? 'text-red-500' : 'text-red-700'}`}>Weakest</p>
                <p className={`font-semibold ${dark ? 'text-gray-200' : 'text-gray-800'}`}>{radar_data.weakest}</p>
              </div>
            </div>
            
            {radar_data.avoided && radar_data.avoided.length > 0 && radar_data.avoided[0] !== "None" && (
              <div className={`mt-4 p-4 rounded-xl border flex gap-3 ${dark ? 'bg-amber-500/5 border-amber-500/20' : 'bg-amber-50 border-amber-200'}`}>
                <AlertTriangle className={`w-5 h-5 flex-shrink-0 ${dark ? 'text-amber-500' : 'text-amber-600'}`} />
                <div>
                  <p className={`text-sm font-semibold mb-1 ${dark ? 'text-amber-400' : 'text-amber-800'}`}>Missed Concept Pillars</p>
                  <p className={`text-sm ${dark ? 'text-gray-300' : 'text-amber-700'}`}>{radar_data.avoided.join(', ')}</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 3. Confidence Map */}
        {confidence_data && (
           <div className={`rounded-3xl p-8 border shadow-sm flex flex-col ${dark ? 'bg-[#141414] border-gray-800' : 'bg-white border-gray-100'}`}>
            <div className="flex justify-between items-start mb-8">
              <div>
                <h3 className={`text-lg font-semibold mb-1 ${dark ? 'text-gray-100' : 'text-gray-900'}`}>Confidence Map</h3>
                <p className={`text-sm ${dark ? 'text-gray-400' : 'text-gray-500'}`}>Turn-by-turn evaluation of delivery.</p>
              </div>
              <div className={`px-4 py-2 rounded-full border text-sm font-semibold flex flex-col items-center ${
                confidence_data.average_score >= 7 ? (dark ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-emerald-50 border-emerald-200 text-emerald-700') :
                confidence_data.average_score >= 5 ? (dark ? 'bg-blue-500/10 border-blue-500/20 text-blue-400' : 'bg-blue-50 border-blue-200 text-blue-700') :
                (dark ? 'bg-red-500/10 border-red-500/20 text-red-400' : 'bg-red-50 border-red-200 text-red-700')
              }`}>
                <span>{confidence_data.average_score} avg</span>
                <span className="text-[10px] uppercase opacity-70 tracking-widest">{confidence_data.trend}</span>
              </div>
            </div>
            
            <div className="flex-1 w-full min-h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={confidence_data.scores} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
                  <XAxis dataKey="turn" axisLine={false} tickLine={false} tick={{ fill: textColor, fontSize: 11 }} tickMargin={10} />
                  <YAxis domain={[0, 10]} axisLine={false} tickLine={false} tick={{ fill: textColor, fontSize: 11 }} />
                  <RechartsTooltip 
                    contentStyle={{ backgroundColor: tooltipBg, borderColor: tooltipBorder, borderRadius: '8px', color: tooltipText, fontSize: '12px' }}
                    labelFormatter={(val) => `Turn ${val}`}
                    formatter={(val, name, props) => {
                      return [val, 'Confidence'];
                    }}
                  />
                  {/* A reference line could be set dynamically. Assuming 5.5 for testing. */}
                  <ReferenceLine y={6} stroke={dark ? '#fbbf24' : '#d97706'} strokeDasharray="3 3" opacity={0.5} label={{ position: 'insideTopLeft', value: 'Avg Bar', fill: textColor, fontSize: 10 }} />
                  
                  <defs>
                    <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="score" stroke="none" fillOpacity={1} fill="url(#colorScore)" />
                  <Line type="monotone" dataKey="score" stroke="#3b82f6" strokeWidth={3} dot={{ r: 4, fill: dark ? '#141414' : '#fff', strokeWidth: 2 }} activeDot={{ r: 6 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            
            <div className={`mt-6 p-4 rounded-xl border text-sm ${dark ? 'bg-gray-800/40 border-gray-700/50 text-gray-300' : 'bg-gray-50 border-gray-200 text-gray-700'}`}>
              <div className="flex justify-between items-center font-medium mb-2 border-b border-gray-200/20 pb-2">
                <span>Peak Moment: Turn {confidence_data.peak_turn}</span>
                <span>Drop: Turn {confidence_data.drop_turn}</span>
              </div>
              <p className="opacity-80 leading-relaxed text-[13px]">
                Hover over the data points in the chart to review specific notes for each turn.
              </p>
            </div>
           </div>
        )}

      </div>
    </div>
  );
}
