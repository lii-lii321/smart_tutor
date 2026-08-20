import client from "./client";

export const financialApi = {
  list: (page = 1, pageSize = 50) =>
    client
      .get("/financial-records/", { params: { page, page_size: pageSize } })
      .then((r) => r.data),
};
