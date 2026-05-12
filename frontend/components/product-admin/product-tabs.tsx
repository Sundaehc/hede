import { BRANDS } from "@/lib/brands"
import { TabsList, TabsTrigger } from "@/components/ui/tabs"

export function ProductTabs() {
  return (
    <TabsList className="h-auto w-full flex-wrap justify-start bg-transparent p-0 gap-1">
      {BRANDS.map((item) => (
        <TabsTrigger
          key={item.key}
          value={item.key}
          className="cursor-pointer rounded-lg border border-transparent bg-transparent px-4 py-2 text-sm font-medium text-muted-foreground transition-all duration-150 hover:bg-muted hover:text-foreground data-[state=active]:border-border data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm"
        >
          {item.label}
        </TabsTrigger>
      ))}
    </TabsList>
  )
}
