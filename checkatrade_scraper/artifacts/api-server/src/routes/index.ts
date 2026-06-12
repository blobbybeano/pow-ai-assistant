import { Router, type IRouter } from "express";
import healthRouter from "./health";
import checkatradeRouter from "./checkatrade";
import settingsRouter from "./settings";

const router: IRouter = Router();

router.use(healthRouter);
router.use(settingsRouter);
router.use(checkatradeRouter);

export default router;
