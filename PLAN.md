### FIX JS ERRORS

Fix these errors to conform to out sanitycheck/ logic:

```
/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/api-client.js
   16:25  error  default parameters are forbidden  sanitycheck/JS002
  310:21  error  default parameters are forbidden  sanitycheck/JS002
  310:36  error  default parameters are forbidden  sanitycheck/JS002
  310:56  error  default parameters are forbidden  sanitycheck/JS002
  310:70  error  default parameters are forbidden  sanitycheck/JS002
  337:13  error  defaulting operator is forbidden  sanitycheck/JS004
  350:13  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/auth.js
   69:11  error  catch must not return                  sanitycheck/JS001
   69:11  error  catch must throw (no silent handling)  sanitycheck/JS001
  200:37  error  defaulting operator is forbidden       sanitycheck/JS004
  204:11  error  catch must throw (no silent handling)  sanitycheck/JS001
  229:15  error  catch must throw (no silent handling)  sanitycheck/JS001
  244:17  error  default parameters are forbidden       sanitycheck/JS002

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/comment-utils.js
  59:21  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/connectivity-monitor.js
  89:11  error  catch must throw (no silent handling)  sanitycheck/JS001

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/dom-utils-fixed.js
   95:59  error  defaulting operator is forbidden            sanitycheck/JS004
  116:33  error  try block has no allowlisted external call  sanitycheck/JS001
  233:40  error  defaulting operator is forbidden            sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/dom-utils.js
   80:32  error  default parameters are forbidden            sanitycheck/JS002
  133:23  error  defaulting operator is forbidden            sanitycheck/JS004
  154:9   error  try block has no allowlisted external call  sanitycheck/JS001
  270:16  error  defaulting operator is forbidden            sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/editor-commands.js
  42:34  error  default parameters are forbidden  sanitycheck/JS002

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/editor-selection.js
  53:29  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/editor-toolbar.js
   31:39  error  defaulting operator is forbidden            sanitycheck/JS004
   54:19  error  defaulting operator is forbidden            sanitycheck/JS004
   67:5   error  try block has no allowlisted external call  sanitycheck/JS001
   69:7   error  catch must not return                       sanitycheck/JS001
   69:7   error  catch must throw (no silent handling)       sanitycheck/JS001
  129:19  error  defaulting operator is forbidden            sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/error-handler.js
   13:27  error  default parameters are forbidden  sanitycheck/JS002
   46:21  error  default parameters are forbidden  sanitycheck/JS002
   54:24  error  default parameters are forbidden  sanitycheck/JS002
  149:40  error  default parameters are forbidden  sanitycheck/JS002
  156:30  error  default parameters are forbidden  sanitycheck/JS002
  156:46  error  default parameters are forbidden  sanitycheck/JS002
  156:63  error  default parameters are forbidden  sanitycheck/JS002
  206:32  error  default parameters are forbidden  sanitycheck/JS002
  213:29  error  default parameters are forbidden  sanitycheck/JS002

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/error-overlay.js
  44:17  error  defaulting operator is forbidden  sanitycheck/JS004
  45:19  error  defaulting operator is forbidden  sanitycheck/JS004
  51:17  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/modals/base-modal.js
   20:31  error  defaulting operator is forbidden  sanitycheck/JS004
  303:16  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/modals/memory-modal.js
  109:25  error  default parameters are forbidden       sanitycheck/JS002
  156:32  error  defaulting operator is forbidden       sanitycheck/JS004
  169:11  error  catch must not return                  sanitycheck/JS001
  169:11  error  catch must throw (no silent handling)  sanitycheck/JS001

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/modals/password-modal.js
   68:11  error  catch must throw (no silent handling)       sanitycheck/JS001
  366:9   error  try block has no allowlisted external call  sanitycheck/JS001
  390:11  error  catch must throw (no silent handling)       sanitycheck/JS001

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/actions/history-actions.js
  142:28  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/actions/note-actions.js
   87:5  error  try without catch is forbidden  sanitycheck/JS001
  224:5  error  try without catch is forbidden  sanitycheck/JS001
  261:5  error  try without catch is forbidden  sanitycheck/JS001

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/actions/selection-actions.js
   10:48  error  default parameters are forbidden            sanitycheck/JS002
   12:9   error  destructuring defaults are forbidden        sanitycheck/JS003
   49:5   error  try block has no allowlisted external call  sanitycheck/JS001
   51:7   error  catch must throw (no silent handling)       sanitycheck/JS001
  142:52  error  default parameters are forbidden            sanitycheck/JS002
  144:9   error  destructuring defaults are forbidden        sanitycheck/JS003
  194:5   error  try block has no allowlisted external call  sanitycheck/JS001
  196:7   error  catch must throw (no silent handling)       sanitycheck/JS001

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/actions/ui-actions.js
   91:51  error  default parameters are forbidden  sanitycheck/JS002
  114:22  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/events/focus-events.js
  78:40  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/events/input-events.js
   51:24  error  defaulting operator is forbidden  sanitycheck/JS004
   58:25  error  defaulting operator is forbidden  sanitycheck/JS004
  210:12  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/events/keyboard-events.js
    59:9   error  defaulting operator is forbidden            sanitycheck/JS004
    90:31  error  defaulting operator is forbidden            sanitycheck/JS004
    92:33  error  defaulting operator is forbidden            sanitycheck/JS004
   118:24  error  defaulting operator is forbidden            sanitycheck/JS004
   126:25  error  defaulting operator is forbidden            sanitycheck/JS004
   139:13  error  defaulting operator is forbidden            sanitycheck/JS004
   296:40  error  defaulting operator is forbidden            sanitycheck/JS004
   375:23  error  defaulting operator is forbidden            sanitycheck/JS004
   409:50  error  default parameters are forbidden            sanitycheck/JS002
   418:39  error  defaulting operator is forbidden            sanitycheck/JS004
   453:41  error  default parameters are forbidden            sanitycheck/JS002
   462:39  error  defaulting operator is forbidden            sanitycheck/JS004
   856:5   error  try block has no allowlisted external call  sanitycheck/JS001
   877:9   error  try block has no allowlisted external call  sanitycheck/JS001
   905:11  error  catch must throw (no silent handling)       sanitycheck/JS001
   911:7   error  catch must throw (no silent handling)       sanitycheck/JS001
   995:49  error  defaulting operator is forbidden            sanitycheck/JS004
  1115:25  error  defaulting operator is forbidden            sanitycheck/JS004
  1216:31  error  defaulting operator is forbidden            sanitycheck/JS004
  1217:28  error  defaulting operator is forbidden            sanitycheck/JS004
  1320:42  error  default parameters are forbidden            sanitycheck/JS002
  1349:5   error  try without catch is forbidden              sanitycheck/JS001
  1448:30  error  defaulting operator is forbidden            sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/mode-context.js
   170:30  error  default parameters are forbidden            sanitycheck/JS002
   269:28  error  defaulting operator is forbidden            sanitycheck/JS004
   270:28  error  defaulting operator is forbidden            sanitycheck/JS004
   521:28  error  defaulting operator is forbidden            sanitycheck/JS004
   589:24  error  default parameters are forbidden            sanitycheck/JS002
   589:41  error  default parameters are forbidden            sanitycheck/JS002
   604:28  error  default parameters are forbidden            sanitycheck/JS002
   644:13  error  try block has no allowlisted external call  sanitycheck/JS001
   646:15  error  catch must throw (no silent handling)       sanitycheck/JS001
   735:29  error  defaulting operator is forbidden            sanitycheck/JS004
   792:23  error  default parameters are forbidden            sanitycheck/JS002
   860:23  error  defaulting operator is forbidden            sanitycheck/JS004
   867:31  error  default parameters are forbidden            sanitycheck/JS002
   871:23  error  defaulting operator is forbidden            sanitycheck/JS004
   888:16  error  defaulting operator is forbidden            sanitycheck/JS004
  1003:28  error  default parameters are forbidden            sanitycheck/JS002
  1018:37  error  defaulting operator is forbidden            sanitycheck/JS004
  1104:36  error  defaulting operator is forbidden            sanitycheck/JS004
  1106:36  error  defaulting operator is forbidden            sanitycheck/JS004
  1108:35  error  defaulting operator is forbidden            sanitycheck/JS004
  1112:37  error  defaulting operator is forbidden            sanitycheck/JS004
  1113:37  error  defaulting operator is forbidden            sanitycheck/JS004
  1114:36  error  defaulting operator is forbidden            sanitycheck/JS004
  1136:37  error  default parameters are forbidden            sanitycheck/JS002
  1152:47  error  default parameters are forbidden            sanitycheck/JS002
  1156:48  error  default parameters are forbidden            sanitycheck/JS002
  1168:24  error  default parameters are forbidden            sanitycheck/JS002
  1169:29  error  defaulting operator is forbidden            sanitycheck/JS004
  1202:13  error  try without catch is forbidden              sanitycheck/JS001
  1281:26  error  default parameters are forbidden            sanitycheck/JS002
  1282:29  error  defaulting operator is forbidden            sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/mode-logger.js
  11:35  error  default parameters are forbidden  sanitycheck/JS002
  11:46  error  default parameters are forbidden  sanitycheck/JS002
  11:76  error  default parameters are forbidden  sanitycheck/JS002
  18:39  error  default parameters are forbidden  sanitycheck/JS002
  22:46  error  default parameters are forbidden  sanitycheck/JS002
  37:35  error  default parameters are forbidden  sanitycheck/JS002
  41:34  error  default parameters are forbidden  sanitycheck/JS002

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/mode-manager-controller.js
  22:16  error  default parameters are forbidden  sanitycheck/JS002

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/services/collapse-affordance-service.js
  38:43  error  default parameters are forbidden  sanitycheck/JS002
  68:25  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/services/differential-view-service.js
   20:23  error  defaulting operator is forbidden      sanitycheck/JS004
   21:23  error  defaulting operator is forbidden      sanitycheck/JS004
   22:25  error  defaulting operator is forbidden      sanitycheck/JS004
   68:34  error  defaulting operator is forbidden      sanitycheck/JS004
   74:60  error  defaulting operator is forbidden      sanitycheck/JS004
   82:40  error  defaulting operator is forbidden      sanitycheck/JS004
   94:34  error  defaulting operator is forbidden      sanitycheck/JS004
  108:60  error  defaulting operator is forbidden      sanitycheck/JS004
  115:40  error  defaulting operator is forbidden      sanitycheck/JS004
  116:34  error  defaulting operator is forbidden      sanitycheck/JS004
  121:25  error  defaulting operator is forbidden      sanitycheck/JS004
  213:59  error  default parameters are forbidden      sanitycheck/JS002
  213:76  error  default parameters are forbidden      sanitycheck/JS002
  283:28  error  defaulting operator is forbidden      sanitycheck/JS004
  312:12  error  defaulting operator is forbidden      sanitycheck/JS004
  344:48  error  default parameters are forbidden      sanitycheck/JS002
  357:28  error  defaulting operator is forbidden      sanitycheck/JS004
  366:59  error  defaulting operator is forbidden      sanitycheck/JS004
  374:23  error  defaulting operator is forbidden      sanitycheck/JS004
  378:21  error  defaulting operator is forbidden      sanitycheck/JS004
  386:31  error  defaulting operator is forbidden      sanitycheck/JS004
  456:26  error  defaulting operator is forbidden      sanitycheck/JS004
  457:29  error  defaulting operator is forbidden      sanitycheck/JS004
  464:26  error  defaulting operator is forbidden      sanitycheck/JS004
  466:38  error  defaulting operator is forbidden      sanitycheck/JS004
  469:35  error  defaulting operator is forbidden      sanitycheck/JS004
  475:29  error  defaulting operator is forbidden      sanitycheck/JS004
  512:23  error  defaulting operator is forbidden      sanitycheck/JS004
  576:31  error  defaulting operator is forbidden      sanitycheck/JS004
  627:21  error  destructuring defaults are forbidden  sanitycheck/JS003
  633:21  error  defaulting operator is forbidden      sanitycheck/JS004
  679:35  error  defaulting operator is forbidden      sanitycheck/JS004
  709:19  error  defaulting operator is forbidden      sanitycheck/JS004
  763:27  error  defaulting operator is forbidden      sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/services/infinite-scroll-service.js
  12:19  error  defaulting operator is forbidden  sanitycheck/JS004
  68:24  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/services/polling-service.js
  54:7  error  catch must throw (no silent handling)       sanitycheck/JS001
  61:5  error  try block has no allowlisted external call  sanitycheck/JS001
  77:7  error  catch must throw (no silent handling)       sanitycheck/JS001

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/services/scroll-anchor-service.js
   51:12  error  defaulting operator is forbidden  sanitycheck/JS004
  111:37  error  default parameters are forbidden  sanitycheck/JS002
  112:27  error  defaulting operator is forbidden  sanitycheck/JS004
  118:23  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/services/scroll-restoration-service.js
   72:24  error  defaulting operator is forbidden  sanitycheck/JS004
  100:54  error  default parameters are forbidden  sanitycheck/JS002
  110:24  error  defaulting operator is forbidden  sanitycheck/JS004
  133:24  error  defaulting operator is forbidden  sanitycheck/JS004
  154:44  error  default parameters are forbidden  sanitycheck/JS002

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/services/tab-dom-cache-service.js
   66:63  error  default parameters are forbidden  sanitycheck/JS002
  107:22  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/services/tab-state-service.js
   64:40  error  default parameters are forbidden  sanitycheck/JS002
   68:52  error  default parameters are forbidden  sanitycheck/JS002
  138:41  error  defaulting operator is forbidden  sanitycheck/JS004

/Users/thomaslahore/Desktop/MetaList3/app/static/js/modules/mode-manager/services/tag-bar-service.js
  267:28  error  defaulting operator is forbidden  sanitycheck/JS004
```