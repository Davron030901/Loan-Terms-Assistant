import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Loan Terms Assistant";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          background: "linear-gradient(135deg, #0b0616 0%, #1a1033 55%, #201548 100%)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 32 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 16,
              background: "linear-gradient(135deg, #8b5cf6, #4f46e5)",
            }}
          />
          <div style={{ color: "#c4b5fd", fontSize: 26, letterSpacing: -0.5 }}>
            Loan Terms Assistant
          </div>
        </div>
        <div style={{ color: "white", fontSize: 76, fontWeight: 700, lineHeight: 1.05, letterSpacing: -2 }}>
          Answers straight from
        </div>
        <div style={{ fontSize: 76, fontWeight: 700, lineHeight: 1.05, letterSpacing: -2, color: "#a78bfa" }}>
          the loan contract.
        </div>
        <div style={{ color: "#94a3b8", fontSize: 28, marginTop: 32 }}>
          Scoped · Grounded · Cited — and it refuses everything else
        </div>
      </div>
    ),
    size,
  );
}
