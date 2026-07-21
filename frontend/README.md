This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

Use Node.js 22 (the production Docker image uses Node 22) and pnpm 10. The
workspace declaration in `pnpm-workspace.yaml` is required so the checked-in
Vitest 3 toolchain is installed instead of falling back to an incompatible
temporary Vitest version.

```bash
corepack enable
corepack prepare pnpm@10.28.2 --activate
pnpm install --frozen-lockfile
pnpm test
```

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Tavily Web Search Provider

DeepSpace can use Tavily for opt-in web search. Add a Tavily connection from
`Dashboard -> Settings -> Providers -> Web`, keep the base URL as `https://api.tavily.com`, and
store the Tavily API key through the provider form. The key is sent to the backend provider API and
stored through the existing encrypted provider-secret flow.

The DeepSpace composer exposes a Web toggle. When enabled, the backend searches through the
configured Tavily provider for that turn, then injects bounded Tavily results into the LLM context.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
