<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import TeacherTabbar from "@/components/TeacherTabbar.vue";

const router = useRouter();
const activeFaqs = ref<number[]>([]);

const faqs = [
  {
    question: "接单的完整流程是什么？",
    answer:
      "确认订单适合后先投递简历，并支付 100 元定金；简历通过后补齐信息费尾款，再与家长沟通试课时间。建议投递前先确认时间、地点、科目和课酬，避免通过简历后无法到岗。",
    actionLabel: "查看我的投递",
    action: () => router.push("/teacher/applications"),
  },
  {
    question: "定金为什么是 100 元？",
    answer:
      "100 元定金用于确认老师的投递意愿，避免家长同意安排后老师单方面不去。定金是信息费的一部分，不会额外多收；简历未通过会全额退回。若在投递中或简历通过后因老师个人原因放弃，定金不予退还。",
  },
  {
    question: "信息费怎么计算？",
    answer:
      "常规单按单次课酬乘以单次时长，再乘频率系数计算：每周 1 次为 1.5 倍、2 次为 1.0 倍、3 次为 0.9 倍、4 次及以上为 0.8 倍；寒暑假单为 2.5 倍。举例：每周 1 次、每次 2 小时、80 元/小时的信息费为 80 x 2 x 1.5 = 240 元，其中已付的 100 元定金会计入这笔费用。",
  },
  {
    question: "什么时候能知道简历结果？",
    answer:
      "家长查看并回复简历后就会有结果，具体速度会因家长安排不同而变化。若超过 24 小时仍未得到回复，定金会自动退回。建议使用微信转账支付定金，便于自动原路退回。",
    actionLabel: "查看投递进度",
    action: () => router.push("/teacher/applications"),
  },
  {
    question: "简历未通过、试课失败，费用怎么处理？",
    answer:
      "简历未通过时，100 元定金全额退回。试课未能达成后续合作时，会按照平台规则退还相应的信息费；信息费只收取一次，已支付的定金会直接抵扣信息费，不会重复收费。",
    actionLabel: "查看投递记录",
    action: () => router.push("/teacher/applications"),
  },
  {
    question: "订单显示“自带价”怎么办？",
    answer:
      "“自带价”订单暂未标注固定课酬，投递时请填写自己的期望课酬，后续会据此进行审核和沟通。提交前请结合授课时间、地点和自身经验谨慎报价。",
    actionLabel: "去找订单",
    action: () => router.push("/teacher/board/tx886"),
  },
];
</script>

<template>
  <div class="min-h-screen bg-slate-50 pb-24">
    <van-nav-bar title="帮助中心" left-arrow @click-left="router.back()" />

    <section class="mx-4 mt-3 rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="text-lg font-semibold text-slate-950">接单常见问题</div>
      <div class="mt-1 text-sm leading-6 text-slate-500">
        投递前先确认规则，费用和流程都更清楚。
      </div>

      <van-collapse v-model="activeFaqs" class="mt-4">
        <van-collapse-item v-for="(item, index) in faqs" :key="item.question" :name="index">
          <template #title>
            <div class="pr-3 text-left text-sm font-medium text-slate-900">
              {{ item.question }}
            </div>
          </template>
          <div class="text-sm leading-7 text-slate-600">
            {{ item.answer }}
          </div>
          <button
            v-if="item.actionLabel"
            class="mt-3 text-sm font-medium text-blue-600"
            @click.stop="item.action?.()"
          >
            {{ item.actionLabel }}
          </button>
        </van-collapse-item>
      </van-collapse>
    </section>

    <section class="mx-4 mt-4 rounded-xl bg-white px-4 py-4 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="text-sm font-medium text-slate-900">投递前再确认一次</div>
      <div class="mt-2 text-sm leading-6 text-slate-500">
        请在订单详情中确认授课需求、时间地点、课酬以及信息费金额，确认能稳定安排再投递。
      </div>
      <button class="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white" @click="router.push('/teacher/board/tx886')">
        去找订单
      </button>
    </section>

    <TeacherTabbar />
  </div>
</template>
