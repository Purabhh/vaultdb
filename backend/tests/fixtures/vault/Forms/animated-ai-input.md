# Animated AI Input
**Source:** 21st.dev / kokonutd
**Tags:** input, ai, chat, model-selector, textarea, animated
**Dependencies:** framer-motion, lucide-react, shadcn (textarea, button, dropdown-menu), tailwind

![Preview](https://21st.dev/kokonutd/animated-ai-input/opengraph-image)

## Code

```tsx
"use client";
import { ArrowRight, Bot, Check, ChevronDown, Paperclip } from "lucide-react";
import { useState, useRef, useCallback, useEffect } from "react";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { motion, AnimatePresence } from "framer-motion";

function useAutoResizeTextarea({ minHeight, maxHeight }: { minHeight: number; maxHeight?: number }) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const adjustHeight = useCallback((reset?: boolean) => {
    const textarea = textareaRef.current; if (!textarea) return;
    if (reset) { textarea.style.height = `${minHeight}px`; return; }
    textarea.style.height = `${minHeight}px`;
    textarea.style.height = `${Math.max(minHeight, Math.min(textarea.scrollHeight, maxHeight ?? Infinity))}px`;
  }, [minHeight, maxHeight]);
  useEffect(() => { if (textareaRef.current) textareaRef.current.style.height = `${minHeight}px`; }, [minHeight]);
  return { textareaRef, adjustHeight };
}

export function AI_Prompt() {
  const [value, setValue] = useState("");
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({ minHeight: 72, maxHeight: 300 });
  const [selectedModel, setSelectedModel] = useState("GPT-4-1 Mini");
  const AI_MODELS = ["o3-mini", "Gemini 2.5 Flash", "Claude 3.5 Sonnet", "GPT-4-1 Mini", "GPT-4-1"];

  return (
    <div className="w-4/6 py-4">
      <div className="bg-black/5 dark:bg-white/5 rounded-2xl p-1.5">
        <div className="relative flex flex-col">
          <div className="overflow-y-auto" style={{ maxHeight: "400px" }}>
            <Textarea id="ai-input" value={value} placeholder="What can I do for you?"
              className={cn("w-full rounded-xl rounded-b-none px-4 py-3 bg-black/5 dark:bg-white/5 border-none dark:text-white placeholder:text-black/70 dark:placeholder:text-white/70 resize-none focus-visible:ring-0", "min-h-[72px]")}
              ref={textareaRef}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && value.trim()) { e.preventDefault(); setValue(""); adjustHeight(true); } }}
              onChange={(e) => { setValue(e.target.value); adjustHeight(); }} />
          </div>
          <div className="h-14 bg-black/5 dark:bg-white/5 rounded-b-xl flex items-center">
            <div className="absolute left-3 right-3 bottom-3 flex items-center justify-between w-[calc(100%-24px)]">
              <div className="flex items-center gap-2">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" className="flex items-center gap-1 h-8 pl-1 pr-2 text-xs rounded-md dark:text-white hover:bg-black/10 dark:hover:bg-white/10">
                      <AnimatePresence mode="wait">
                        <motion.div key={selectedModel} initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 5 }} transition={{ duration: 0.15 }} className="flex items-center gap-1">
                          {selectedModel} <ChevronDown className="w-3 h-3 opacity-50" />
                        </motion.div>
                      </AnimatePresence>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    {AI_MODELS.map((model) => (
                      <DropdownMenuItem key={model} onSelect={() => setSelectedModel(model)} className="flex items-center justify-between gap-2">
                        <span>{model}</span>
                        {selectedModel === model && <Check className="w-4 h-4 text-blue-500" />}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
                <div className="h-4 w-px bg-black/10 dark:bg-white/10 mx-0.5" />
                <label className={cn("rounded-lg p-2 bg-black/5 dark:bg-white/5 cursor-pointer hover:bg-black/10 dark:hover:bg-white/10")} aria-label="Attach file">
                  <input type="file" className="hidden" /><Paperclip className="w-4 h-4 transition-colors" />
                </label>
              </div>
              <button type="button" className={cn("rounded-lg p-2 bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10")} aria-label="Send message" disabled={!value.trim()}
                onClick={() => { if (!value.trim()) return; setValue(""); adjustHeight(true); }}>
                <ArrowRight className={cn("w-4 h-4 dark:text-white transition-opacity duration-200", value.trim() ? "opacity-100" : "opacity-30")} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

## Usage Notes
AI chat input with auto-resizing textarea, model selector dropdown with animated transitions, file attachment, and send button. Perfect for AI agent interfaces, chatbot UIs.
