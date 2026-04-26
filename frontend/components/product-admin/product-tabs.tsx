import { BRANDS } from "@/lib/brands"
import { TabsList, TabsTrigger } from "@/components/ui/tabs"

export function ProductTabs() {
  return (
    <TabsList className="h-auto flex-wrap justify-start bg-transparent p-0">
      {BRANDS.map((item) => (
        <TabsTrigger
          key={item.key}
          value={item.key}
          className="cursor-pointer border border-border bg-background data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
        >
          {item.label}
        </TabsTrigger>
      ))}
    </TabsList>
  )
}
