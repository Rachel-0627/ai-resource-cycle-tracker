import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LabelTag from "./LabelTag";

describe("LabelTag", () => {
  it("renders known labels", () => {
    render(<LabelTag label="High Priority" />);

    expect(screen.getByText("High Priority")).toBeInTheDocument();
  });

  it("falls back to replay when label is missing", () => {
    render(<LabelTag label={null} />);

    expect(screen.getByText("replay")).toBeInTheDocument();
  });
});
