import type { PublicConfig } from "../api/types";
import { AttentionStrip } from "../widgets/Attention";
import { BenefitsWidget } from "../widgets/Benefits";
import { CalendarWidget } from "../widgets/Calendar";
import { CardsWidget } from "../widgets/Cards";
import { ContainersWidget } from "../widgets/Containers";
import { FinanceWidget } from "../widgets/Finance";
import { PlexWidget } from "../widgets/Plex";
import { RecurringWidget } from "../widgets/Recurring";
import { ServiceHealthRow } from "../widgets/ServiceHealth";
import { VaultWidget } from "../widgets/Vault";
import { WeatherWidget } from "../widgets/Weather";

export function Dashboard({ config, readOnly }: { config?: PublicConfig; readOnly: boolean }) {
  return (
    <main className="mx-auto max-w-[1600px] space-y-4 px-4 py-4">
      <AttentionStrip location={config?.selected_location} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="order-1 min-w-0 lg:order-none lg:col-span-8">
          <CalendarWidget />
        </div>
        <div className="order-2 min-w-0 lg:order-none lg:col-span-4">
          <WeatherWidget location={config?.selected_location} />
        </div>
        <div className="order-4 min-w-0 space-y-4 lg:order-none lg:col-span-8">
          <FinanceWidget syncEnabled={!!config?.features.finance_sync && !readOnly} />
          <RecurringWidget readOnly={readOnly} />
        </div>
        <div className="order-3 min-w-0 space-y-4 lg:order-none lg:col-span-4">
          <CardsWidget />
          <BenefitsWidget />
        </div>
        <div className="order-6 min-w-0 lg:order-none lg:col-span-8">
          <PlexWidget />
        </div>
        <div className="order-7 min-w-0 space-y-4 lg:order-none lg:col-span-4">
          <VaultWidget />
          <ServiceHealthRow />
        </div>
        <div className="order-5 min-w-0 lg:order-none lg:col-span-12">
          <ContainersWidget readOnly={readOnly} />
        </div>
      </div>
    </main>
  );
}
