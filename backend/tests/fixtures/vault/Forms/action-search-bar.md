# Action Search Bar
**Source:** 21st.dev / kokonutd
**Tags:** search, command-palette, raycast, actions, animated
**Dependencies:** framer-motion, lucide-react, shadcn/input, tailwind

![Preview](https://21st.dev/kokonutd/action-search-bar/opengraph-image)

## Code

```tsx
"use client";
import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Send, BarChart2, Globe, Video, PlaneTakeoff, AudioLines } from "lucide-react";

function useDebounce<T>(value: T, delay: number = 500): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => { const timer = setTimeout(() => setDebouncedValue(value), delay); return () => clearTimeout(timer); }, [value, delay]);
  return debouncedValue;
}

export interface Action { id: string; label: string; icon: React.ReactNode; description?: string; short?: string; end?: string; }

const allActions: Action[] = [
  { id: "1", label: "Book tickets", icon: <PlaneTakeoff className="h-4 w-4 text-blue-500" />, description: "Operator", short: "⌘K", end: "Agent" },
  { id: "2", label: "Summarize", icon: <BarChart2 className="h-4 w-4 text-orange-500" />, description: "gpt-4o", short: "⌘cmd+p", end: "Command" },
  { id: "3", label: "Screen Studio", icon: <Video className="h-4 w-4 text-purple-500" />, description: "gpt-4o", end: "Application" },
  { id: "4", label: "Talk to Jarvis", icon: <AudioLines className="h-4 w-4 text-green-500" />, description: "gpt-4o voice", end: "Active" },
  { id: "5", label: "Translate", icon: <Globe className="h-4 w-4 text-blue-500" />, description: "gpt-4o", end: "Command" },
];

function ActionSearchBar({ actions = allActions }: { actions?: Action[] }) {
  const [query, setQuery] = useState(""); const [result, setResult] = useState<{ actions: Action[] } | null>(null);
  const [isFocused, setIsFocused] = useState(false); const [selectedAction, setSelectedAction] = useState<Action | null>(null);
  const debouncedQuery = useDebounce(query, 200);

  useEffect(() => {
    if (!isFocused) { setResult(null); return; }
    if (!debouncedQuery) { setResult({ actions: allActions }); return; }
    setResult({ actions: allActions.filter((a) => a.label.toLowerCase().includes(debouncedQuery.toLowerCase().trim())) });
  }, [debouncedQuery, isFocused]);

  return (
    <div className="w-full max-w-xl mx-auto">
      <div className="relative flex flex-col justify-start items-center min-h-[300px]">
        <div className="w-full max-w-sm sticky top-0 bg-background z-10 pt-4 pb-1">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1 block">Search Commands</label>
          <div className="relative">
            <Input type="text" placeholder="What's up?" value={query} onChange={(e) => setQuery(e.target.value)}
              onFocus={() => { setSelectedAction(null); setIsFocused(true); }} onBlur={() => setTimeout(() => setIsFocused(false), 200)}
              className="pl-3 pr-9 py-1.5 h-9 text-sm rounded-lg" />
            <div className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4">
              <AnimatePresence mode="popLayout">
                {query.length > 0 ? (
                  <motion.div key="send" initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 20, opacity: 0 }}><Send className="w-4 h-4 text-gray-400" /></motion.div>
                ) : (
                  <motion.div key="search" initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 20, opacity: 0 }}><Search className="w-4 h-4 text-gray-400" /></motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
        <div className="w-full max-w-sm">
          <AnimatePresence>
            {isFocused && result && !selectedAction && (
              <motion.div className="w-full border rounded-md shadow-sm overflow-hidden dark:border-gray-800 bg-white dark:bg-black mt-1"
                initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
                <motion.ul>
                  {result.actions.map((action) => (
                    <motion.li key={action.id} className="px-3 py-2 flex items-center justify-between hover:bg-gray-200 dark:hover:bg-zinc-900 cursor-pointer rounded-md"
                      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} onClick={() => setSelectedAction(action)}>
                      <div className="flex items-center gap-2">
                        <span className="text-gray-500">{action.icon}</span>
                        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{action.label}</span>
                        <span className="text-xs text-gray-400">{action.description}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-400">{action.short}</span>
                        <span className="text-xs text-gray-400">{action.end}</span>
                      </div>
                    </motion.li>
                  ))}
                </motion.ul>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

export { ActionSearchBar };
```

## Usage Notes
Raycast-inspired command palette search bar with debounced filtering, animated icon swap (search/send), staggered results. Great for AI agent UIs, dashboards, command interfaces.
