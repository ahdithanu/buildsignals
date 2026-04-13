import { Layout } from "@/components/Layout";
import { motion } from "framer-motion";
import { Settings as SettingsIcon, Scale, FileText, Bell, Database, Users, Plug } from "lucide-react";

const fadeIn = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };

const settingsSections = [
  {
    icon: <SettingsIcon className="h-4 w-4" />,
    title: 'Workspace Settings',
    description: 'Configure workspace name, branding, and default preferences.',
    items: ['Workspace name', 'Logo', 'Default currency', 'Timezone'],
  },
  {
    icon: <Scale className="h-4 w-4" />,
    title: 'Scoring Weights',
    description: 'Customize how deal scores are calculated across dimensions.',
    items: ['Market attractiveness weight', 'Financial upside weight', 'Operational complexity weight', 'Permitting risk weight', 'Execution speed weight'],
  },
  {
    icon: <FileText className="h-4 w-4" />,
    title: 'Memo Templates',
    description: 'Manage investment memo templates and formatting preferences.',
    items: ['Default template', 'Custom sections', 'Header/footer', 'Branding'],
  },
  {
    icon: <Bell className="h-4 w-4" />,
    title: 'Notification Preferences',
    description: 'Control how and when you receive alerts about deal activity.',
    items: ['Email notifications', 'In-app alerts', 'Signal notifications', 'Weekly digest'],
  },
  {
    icon: <Database className="h-4 w-4" />,
    title: 'Data Sources',
    description: 'Connect and manage external data feeds for market intelligence.',
    items: ['CoStar integration', 'Public records', 'Census data', 'Permit feeds'],
  },
  {
    icon: <Users className="h-4 w-4" />,
    title: 'Team Members',
    description: 'Manage team access, roles, and permissions.',
    items: ['Sarah Chen — Managing Director', 'Marcus Reid — VP Acquisitions', 'Elena Voss — Senior Analyst', 'James Park — Analyst'],
  },
  {
    icon: <Plug className="h-4 w-4" />,
    title: 'API Connections',
    description: 'Manage API keys and integrations with external platforms.',
    items: ['Enrichment API', 'Document processing', 'CRM sync', 'Email integration'],
  },
];

export default function Settings() {
  return (
    <Layout>
      <div className="p-6 max-w-[900px] mx-auto">
        <motion.div {...fadeIn} className="mb-6">
          <h2 className="text-xl font-semibold font-display text-foreground">Settings</h2>
          <p className="text-sm text-muted-foreground mt-0.5">Configure your Deal Engine workspace</p>
        </motion.div>

        <div className="space-y-4">
          {settingsSections.map((section, i) => (
            <motion.div key={i} {...fadeIn} transition={{ delay: i * 0.05 }}>
              <div className="rounded-xl border bg-card p-5 card-shadow hover:card-shadow-hover transition-shadow">
                <div className="flex items-start gap-4">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                    {section.icon}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-foreground">{section.title}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">{section.description}</p>
                    <div className="flex flex-wrap gap-2 mt-3">
                      {section.items.map((item, j) => (
                        <span key={j} className="text-xs bg-secondary px-2.5 py-1 rounded-md text-muted-foreground">
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                  <button className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5 rounded-lg bg-secondary">
                    Configure
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
