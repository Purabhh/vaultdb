# Collapsible Four
**Source:** 21st.dev / ShadcnStudio
**Tags:** collapsible, expandable, toggle, radix
**Dependencies:** @radix-ui/react-collapsible, lucide-react, tailwind

![Preview](https://21st.dev/ShadcnStudio/collapsible-four/opengraph-image)

## Code

```tsx
"use client"

import * as React from "react"
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible"
import { cn } from "@/lib/utils"
import { ChevronsUpDownIcon } from "lucide-react"
import { Button } from "@/components/ui/button"

const Collapsible = CollapsiblePrimitive.Root
const CollapsibleTrigger = CollapsiblePrimitive.Trigger
const CollapsibleContent = CollapsiblePrimitive.Content

export { Collapsible, CollapsibleTrigger, CollapsibleContent }

// Example usage:
export function CollapsibleFourDemo() {
  return (
    <Collapsible className="flex w-full max-w-[350px] flex-col gap-2">
      <div className="flex items-center justify-between gap-4 px-4">
        <div className="text-sm font-semibold">Title</div>
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="icon">
            <ChevronsUpDownIcon />
          </Button>
        </CollapsibleTrigger>
      </div>
      <div className="rounded-md border px-4 py-3 text-sm">
        Always visible content
      </div>
      <CollapsibleContent className="space-y-2">
        <div className="rounded-md border px-4 py-3 text-sm">
          Hidden content 1
        </div>
        <div className="rounded-md border px-4 py-3 text-sm">
          Hidden content 2
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
```

## Usage Notes
Good for showing/hiding session details, tutor bios, FAQ items. Lightweight Radix primitive — compose with any content inside. Pair with cards or list items for expandable rows.
