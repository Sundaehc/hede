import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

type ProductToolbarProps = {
  value: string
  isLoading: boolean
  onValueChange: (value: string) => void
  onSearch: () => void
  onClear: () => void
  onRefresh: () => void
  onCreate: () => void
}

export function ProductToolbar({
  value,
  isLoading,
  onValueChange,
  onSearch,
  onClear,
  onRefresh,
  onCreate,
}: ProductToolbarProps) {
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4 md:flex-row md:items-end md:justify-between">
      <div className="flex flex-1 flex-col gap-2">
        <Label htmlFor="product-search-input">原始货号</Label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            id="product-search-input"
            value={value}
            placeholder="请输入原始货号"
            onChange={(event) => onValueChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault()
                onSearch()
              }
            }}
          />
          <div className="flex flex-1 gap-2">
            <Button type="button" onClick={onSearch} disabled={isLoading} className="cursor-pointer">
              搜索
            </Button>
            <Button type="button" variant="outline" onClick={onClear} disabled={isLoading && value.length === 0} className="cursor-pointer">
              清空
            </Button>
            <Button type="button" variant="outline" onClick={onRefresh} disabled={isLoading} className="cursor-pointer">
              刷新
            </Button>
            <Button type="button" variant="secondary" onClick={onCreate} className="cursor-pointer">
              新增商品
            </Button>
          </div>
        </div>
      </div>


    </div>
  )
}
