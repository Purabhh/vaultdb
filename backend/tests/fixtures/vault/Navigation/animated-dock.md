# Animated Dock
**Source:** 21st.dev / hextaui (Preet Suthar)
**Tags:** dock, navigation, animated, macOS, hover-grow
**Dependencies:** motion/react, clsx, tailwind-merge, next/link, tailwind

![Preview](https://21st.dev/hextaui/animated-dock/opengraph-image)

## Code

```tsx
"use client"
import * as React from "react"
import { useRef } from "react"
import { MotionValue, motion, useMotionValue, useSpring, useTransform } from "motion/react"
import clsx from "clsx"
import { twMerge } from "tailwind-merge"
import Link from "next/link"

const cn = (...args: any[]) => twMerge(clsx(args))

export interface DockItemData { link: string; Icon: React.ReactNode; target?: string; }
export interface AnimatedDockProps { className?: string; items: DockItemData[]; }

export const AnimatedDock = ({ className, items }: AnimatedDockProps) => {
  const mouseX = useMotionValue(Infinity)
  return (
    <motion.div onMouseMove={(e) => mouseX.set(e.pageX)} onMouseLeave={() => mouseX.set(Infinity)}
      className={cn("mx-auto flex h-16 items-end gap-4 rounded-2xl bg-secondary/50 border border-primary/10 shadow-md px-4 pb-3", className)}>
      {items.map((item, index) => (
        <DockItem key={index} mouseX={mouseX}>
          <Link href={item.link} target={item.target} className="grow flex items-center justify-center w-full h-full text-primary-foreground">
            {item.Icon}
          </Link>
        </DockItem>
      ))}
    </motion.div>
  )
}

const DockItem = ({ mouseX, children }: { mouseX: MotionValue<number>; children: React.ReactNode }) => {
  const ref = useRef<HTMLDivElement>(null)
  const distance = useTransform(mouseX, (val) => {
    const bounds = ref.current?.getBoundingClientRect() ?? { x: 0, width: 0 }
    return val - bounds.x - bounds.width / 2
  })
  const widthSync = useTransform(distance, [-150, 0, 150], [40, 80, 40])
  const width = useSpring(widthSync, { mass: 0.1, stiffness: 150, damping: 12 })
  const iconScale = useTransform(width, [40, 80], [1, 1.5])
  const iconSpring = useSpring(iconScale, { mass: 0.1, stiffness: 150, damping: 12 })

  return (
    <motion.div ref={ref} style={{ width }} className="aspect-square w-10 rounded-full bg-primary text-secondary-foreground flex items-center justify-center">
      <motion.div style={{ scale: iconSpring }} className="flex items-center justify-center w-full h-full grow">
        {children}
      </motion.div>
    </motion.div>
  )
}
```

## Usage

```tsx
import { Home, Search, Settings, User } from "lucide-react"

<AnimatedDock items={[
  { link: "/", Icon: <Home className="w-5 h-5" /> },
  { link: "/search", Icon: <Search className="w-5 h-5" /> },
  { link: "/profile", Icon: <User className="w-5 h-5" /> },
  { link: "/settings", Icon: <Settings className="w-5 h-5" /> },
]} />
```

## Usage Notes
macOS-style dock where icons grow as cursor approaches. Uses spring physics for smooth scaling. Pass any icons/links as items. Great for app navigation, dashboard sidebars, bottom nav bars.
